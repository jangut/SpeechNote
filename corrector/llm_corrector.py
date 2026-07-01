"""
LLM Corrector — 大模型文本纠错模块。

Architecture:
┌─────────────┐     ┌──────────────────┐     ┌────────────┐     ┌──────────┐     ┌─────────┐
│ ASR Pipeline │────▶│ SlidingWindowBuf │────▶│   Queue    │────▶│   Worker  │────▶│ Callback│
│ correct()    │     │  (2~3句窗口)     │     │SentenceWin │     │LLM+后处理 │     │ Sentence│
└─────────────┘     └──────────────────┘     └────────────┘     └──────────┘     └─────────┘
                           ▲
                      Timer(idle timeout)
"""

from __future__ import annotations

import logging
import threading
import queue
import time
import random
from dataclasses import dataclass, field
from typing import Callable

import httpx

from core.sentence import Sentence, SourceType
from corrector import BaseCorrector


# ==========================================================
# Configuration
# ==========================================================

@dataclass(slots=True)
class LLMConfig:
    """LLM Corrector 统一配置对象。"""

    # --- 服务商 ---
    provider: str = "ollama"
    base_url: str = "http://localhost:11434/v1/chat/completions"
    api_key: str = "ollama"
    model: str = "qwen3:8b"

    # --- 请求 ---
    request_timeout: float = 15.0       # 单次请求超时（秒）
    max_retries: int = 2                # 最大重试次数

    # --- 窗口策略 ---
    window_max_sentences: int = 3       # 每个窗口最大句子数
    window_max_chars: int = 200         # 每个窗口最大字符数
    idle_timeout: float = 0.6           # 静音触发纠错（秒）
    short_text_threshold: int = 2       # 短文本触发阈值（字数）

    # --- 其他 ---
    prompt_path: str = ""               # 自定义 Prompt 文件路径


# ==========================================================
# Constants
# ==========================================================

_QUEUE_MAXSIZE = 64
_STOP_SENTINEL = object()

_DEFAULT_SYSTEM_PROMPT = """任务：校对 ASR 文本。

规则：
1. 只允许修改以下内容：
   - 错别字
   - 识别错误
   - 标点符号
   - 不通顺的语序
2. 保持原始句子数量不变，每行一句对应输出一句。
3. 不得修改原意。
4. 不得扩写、总结、解释。
5. 不得添加任何不存在的信息。
6. 修改幅度保持最小。

输出格式：
按行输出修正后的句子，一行一句。"""


# ==========================================================
# Data Structures
# ==========================================================

@dataclass(slots=True)
class SentenceWindow:
    """LLM 修正窗口：2~3 句为一个处理单元。"""
    id: int
    sentences: list[Sentence] = field(default_factory=list)
    text: str = ""
    corrected_text: str = ""
    created_at: float = 0.0


class SlidingWindowBuffer:
    """滑动窗口缓冲池。

    将连续的 Sentence 组织成固定大小的窗口。
    每个窗口 2~3 句或达到字符上限后自动就绪。
    """

    def __init__(
        self,
        max_sentences: int = 3,
        max_chars: int = 200,
    ) -> None:
        self._max_sentences = max_sentences
        self._max_chars = max_chars
        self._current: SentenceWindow | None = None
        self._next_id = 1
        self._logger = logging.getLogger(__name__)

    def add(self, sentence: Sentence) -> list[SentenceWindow]:
        """添加一个句子，返回已就绪的窗口列表（0~1个）。"""
        if self._current is None:
            self._current = SentenceWindow(
                id=self._next_id,
                created_at=time.time(),
            )
            self._next_id += 1

        # 带分隔符追加（避免文本粘连）
        delimiter = "" if not self._current.text else " "
        self._current.text += delimiter + sentence.text
        self._current.sentences.append(sentence)

        # 窗口已满 → 就绪
        if self._is_ready():
            ready = self._current
            self._current = None
            return [ready]

        return []

    def _is_ready(self) -> bool:
        """窗口是否已满（句子数或字符数任一达到上限）。"""
        if self._current is None:
            return False
        if len(self._current.sentences) >= self._max_sentences:
            return True
        if len(self._current.text) >= self._max_chars:
            return True
        return False

    def has_pending(self) -> bool:
        """是否存在未提交的窗口内容。"""
        return (
            self._current is not None
            and len(self._current.sentences) > 0
        )

    def flush_current(self) -> SentenceWindow | None:
        """强制取出当前窗口（无论是否已满）。"""
        if not self.has_pending():
            return None
        window = self._current
        self._current = None
        return window

    def reset(self) -> None:
        """重置所有状态。"""
        self._current = None
        self._next_id = 1


# ==========================================================
# LLM Corrector
# ==========================================================

class LLMCorrector(BaseCorrector):

    # ======================================================
    # Lifecycle
    # ======================================================

    def __init__(
        self,
        config: LLMConfig,
        callback: Callable[[Sentence], None] | None = None,
    ) -> None:
        """初始化 LLM Corrector。

        Parameters
        ----------
        config : LLMConfig
            配置对象。
        callback : Callable[[Sentence], None] | None
            修正完成的回调，参数为修正后的 Sentence（llm_corrected=True）。
        """
        self._logger = logging.getLogger(__name__)

        # --- 配置 ---
        self._config = config
        self._idle_timeout = config.idle_timeout
        self._short_text_threshold = config.short_text_threshold
        self._model = config.model
        self._api_key = config.api_key
        self._request_timeout = config.request_timeout
        self._retry_count = config.max_retries
        self._prompt_path = config.prompt_path

        # --- API URL（自动识别 Ollama 原生 / OpenAI 格式） ---
        self._api_url, self._openai_mode = self._resolve_api_url(config.base_url)

        # --- 滑动窗口缓冲 ---
        self._buffer = SlidingWindowBuffer(
            max_sentences=config.window_max_sentences,
            max_chars=config.window_max_chars,
        )

        # --- 队列（传输 SentenceWindow） ---
        self._queue: queue.Queue[object] = queue.Queue(maxsize=_QUEUE_MAXSIZE)

        # --- 线程 ---
        self._worker_thread: threading.Thread | None = None
        self._timer_thread: threading.Thread | None = None
        self._running = False

        # --- Timer 状态 ---
        self._last_input_time = 0.0
        self._flush_lock = threading.Lock()
        self._flushing = False

        # --- System prompt ---
        self._system_prompt = _DEFAULT_SYSTEM_PROMPT

        # --- Callback ---
        self._callback = callback

    @staticmethod
    def _resolve_api_url(base_url: str) -> tuple[str, bool]:
        """解析 API URL，返回 (完整URL, 是否为OpenAI格式)。"""
        base = base_url.strip().rstrip("/")
        if not base:
            base = "http://localhost:11434"
        if base.endswith("/chat/completions"):
            return base, True
        if base.endswith("/v1"):
            return base + "/chat/completions", True
        if "/v1" in base:
            return base + "/chat/completions", True
        return base + "/api/chat", False

    def start(self) -> None:
        """启动后台线程。"""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="LLMWorker", daemon=True,
        )
        self._worker_thread.start()
        self._timer_thread = threading.Thread(
            target=self._timer_loop, name="LLMTimer", daemon=True,
        )
        self._timer_thread.start()
        self._logger.info("LLM Corrector started.")

    def stop(self) -> None:
        """停止后台线程。"""
        if not self._running:
            return
        self._running = False

        # Stop sentinel：通知 worker 线程退出
        try:
            self._queue.put_nowait(_STOP_SENTINEL)
        except queue.Full:
            pass

        if self._worker_thread is not None:
            self._worker_thread.join(timeout=3.0)
        if self._timer_thread is not None:
            self._timer_thread.join(timeout=3.0)

        self._logger.info("LLM Corrector stopped.")

    # ======================================================
    # Public API
    # ======================================================

    def correct(self, sentence: Sentence) -> Sentence:
        """接收 ASR Sentence：输入层 + 透传原句。

        - 将句子输入到滑动窗口缓冲
        - 窗口满后自动提交到处理队列
        - 立即返回原句（透传），不阻塞 pipeline
        - LLM 修正结果通过 callback 返回
        """
        if not self._running:
            return sentence
        if not sentence or not sentence.text or not sentence.text.strip():
            return sentence

        # 输入到滑动窗口
        ready = self._buffer.add(sentence)
        self._last_input_time = time.time()

        # 短文本立即触发提交
        if len(sentence.text) <= self._short_text_threshold:
            self.flush()

        # 提交已就绪的窗口
        for window in ready:
            self._submit_window(window)

        return sentence

    def flush(self) -> None:
        """强制提交当前未满的窗口（带防重复锁）。"""
        with self._flush_lock:
            if self._flushing:
                return
            self._flushing = True

        try:
            window = self._buffer.flush_current()
            if window is not None:
                self._submit_window(window)
        finally:
            self._flushing = False

    # ======================================================
    # Window Submission
    # ======================================================

    def _submit_window(self, window: SentenceWindow) -> None:
        """提交一个窗口到处理队列。"""
        try:
            self._queue.put_nowait(window)
            self._logger.info(
                "提交窗口 id=%d, %d句, %d字",
                window.id, len(window.sentences), len(window.text),
            )
        except queue.Full:
            self._logger.warning("队列已满，丢弃窗口 id=%d", window.id)

    # ======================================================
    # Timer
    # ======================================================

    def _timer_loop(self) -> None:
        """静默超时检测线程（带 jitter 防固定轮询）。"""
        while self._running:
            sleep_time = 0.3 + random.uniform(0, 0.1)
            time.sleep(sleep_time)

            if not self._running:
                break
            if not self._buffer.has_pending():
                continue

            elapsed = time.time() - self._last_input_time
            if elapsed >= self._idle_timeout:
                self._logger.info("静默超时，自动提交")
                self.flush()

    # ======================================================
    # Worker
    # ======================================================

    def _worker_loop(self) -> None:
        """后台线程：消费队列中的 SentenceWindow 并调用 LLM。"""
        while self._running:
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # Stop sentinel
            if item is _STOP_SENTINEL:
                break
            if not isinstance(item, SentenceWindow):
                continue

            try:
                self._process_window(item)
            except Exception as e:
                self._logger.exception("Worker error, re-queue: %s", e)
                # 异常 fallback：重新入队（最多一次）
                try:
                    self._queue.put_nowait(item)
                except queue.Full:
                    self._logger.error("队列满，无法重新入队窗口 id=%d", item.id)

    def _process_window(self, window: SentenceWindow) -> None:
        """处理窗口：调用 LLM 修正，后处理，创建修正后的 Sentence。"""
        if not window.text.strip():
            self._logger.warning("跳过空窗口 id=%d", window.id)
            return

        prompt = self._build_prompt(window)
        result = self._call_llm(prompt)

        if not result or not result.strip():
            self._logger.warning("LLM 返回空结果，窗口 id=%d", window.id)
            return

        # 后处理：行数对齐 + 安全过滤
        result = self._post_filter(result, window)
        window.corrected_text = result

        # 创建修正后的 Sentence
        original = window.sentences[-1] if window.sentences else None
        corrected = Sentence(
            raw_text=window.text,
            text=result,
            start_time=original.start_time if original else 0.0,
            end_time=original.end_time if original else 0.0,
            source=original.source if original else SourceType.MICROPHONE,
            is_final=True,
            llm_corrected=True,
        )

        if self._callback:
            try:
                self._callback(corrected)
            except Exception as e:
                self._logger.exception("Callback error: %s", e)

        self._logger.info(
            "修正完成: 窗口 id=%d, %d句, %d字 -> %d字",
            window.id, len(window.sentences), len(window.text), len(result),
        )

    # ======================================================
    # Prompt Building
    # ======================================================

    def _build_prompt(self, window: SentenceWindow) -> str:
        """构建 Prompt：窗口内句子按行排列。"""
        system_prompt = self._load_prompt()
        input_text = window.text
        return f"{system_prompt}\n\n{input_text}"

    def _load_prompt(self) -> str:
        """加载 Prompt，优先从文件读取。"""
        if self._prompt_path:
            try:
                from pathlib import Path
                path = Path(self._prompt_path)
                if path.exists():
                    return path.read_text(encoding="utf-8")
            except Exception:
                self._logger.warning("读取 Prompt 文件失败: %s", self._prompt_path)
        return self._system_prompt

    # ======================================================
    # Post-processing
    # ======================================================

    @staticmethod
    def _post_filter(result: str, window: SentenceWindow) -> str:
        """二次过滤：行数对齐 + 空行清理。"""
        if not result or not result.strip():
            return result

        result_lines = [line.strip() for line in result.strip().split("\n") if line.strip()]

        # 若 LLM 输出了过多行，截断到接近输入行数
        input_line_count = max(1, len(window.text.strip().split("\n")))
        if len(result_lines) > input_line_count:
            result_lines = result_lines[:input_line_count]

        return "\n".join(result_lines)

    # ======================================================
    # LLM Client
    # ======================================================

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM 接口，带指数退避重试。"""
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "num_predict": 512,
                "temperature": 0.1,
            },
        }

        last_error = None
        for attempt in range(self._retry_count + 1):
            try:
                resp = httpx.post(
                    self._api_url, json=payload, headers=headers,
                    timeout=self._request_timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                if self._openai_mode:
                    return data["choices"][0]["message"]["content"]
                else:
                    return data["message"]["content"]
            except Exception as e:
                last_error = e
                if attempt < self._retry_count:
                    wait = (2 ** attempt) * 0.5  # 指数退避: 0.5s, 1s, 2s
                    self._logger.warning(
                        "LLM 请求失败 (第%d次重试, %.1fs后): %s",
                        attempt + 1, wait, e,
                    )
                    time.sleep(wait)

        self._logger.error("LLM 请求全部失败: %s", last_error)
        return ""
