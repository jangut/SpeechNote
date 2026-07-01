"""
基于大模型的文本纠错器（多缓冲池 + 静默超时版）

特性：
- 累积触发：字数达到阈值（默认 短文本阈值） 或 静默超过 timeout（默认0.6秒）
- 多缓冲池：提交后立即创建新池，未处理的池排队等待
- 上下文串联：每个池处理时参考前一个池的修正结果，保证段落连贯
- 实时推送：每处理完一个池即回调，推送该段修正文本和总结
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import httpx

from core.logger import get_logger
from core.sentence import Sentence
from corrector.base import BaseCorrector

# ── 默认系统 Prompt（批量版）─────────────────────────────
_DEFAULT_SYSTEM_PROMPT = """\
你是一个中文会议文本润色专家。输入是一段包含口语化表达的中文文本（可能含 ASR 错误）。

【核心原则】
1. **仅修正词语**：纠正错别字、专业术语错误（如电路、控制、AI 领域）。除非句子完全不通顺，否则**绝对不要改变原有句式、语序或结构**。
2. **剔除语气词**：删除无意义的填充词，如“嗯”、“啊”、“那个”、“就是说”、“然后”等，使正文简洁。
3. **组织为段落**：将修正后的内容组织成一段连贯、通顺的自然段落，不要以列表或逐句形式输出。
4. **总结与情绪**：在段落末尾，写一段简短的总结（20-30字），概括这段文字的核心内容，并根据原文中的语气词或表达方式，描述说话者的情绪状态（例如：自信、犹豫、激动、严肃、困惑等）。

【输出格式】（必须严格遵守以下标记）
[修正段落]
...（这里输出修正后的段落文本）...
[段落总结]
...（这里输出总结和情绪描述）...
"""

_PROVIDER_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "qwen": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
    "glm": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "ollama": "http://localhost:11434/v1/chat/completions",
}


@dataclass
class _Buffer:
    """一个积累单元（缓冲池）"""
    id: int
    text: str = ""
    sentences: list[Sentence] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)
    status: str = "accumulating"  # accumulating | submitted | processing | done
    corrected_text: Optional[str] = None
    summary: Optional[str] = None
    # 超时任务句柄（用于取消）
    timeout_task: Optional[asyncio.Task] = None


class LLMCorrector(BaseCorrector):
    """
    多缓冲池 + 静默超时版纠错器。
    """

    def __init__(
        self,
        *,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        provider: str = "openai",
        timeout: float = 10.0,          # LLM API 超时
        max_retries: int = 2,
        max_context_sentences: int = 3,     # 上下文参考的句子/缓冲池数（兼容旧参数名）
        idle_timeout: float = 15,          # 静默超时触发纠错（秒）
        short_text_threshold: int = 2,      # 短文本阈值，累计字数达到此值会考虑提交
        prompt_path: str | Path | None = None,
        on_update_callback: Callable[[Sentence], None] | None = None,
    ) -> None:
        self._logger = get_logger()
        self._base_url = base_url or _PROVIDER_URLS.get(provider, _PROVIDER_URLS["openai"])
        self._api_key = api_key
        self._model = model
        self._provider = provider
        self._timeout = timeout
        self._max_retries = max_retries
        self._max_context_buffers = max_context_sentences
        self._idle_timeout = idle_timeout
        self._batch_threshold = short_text_threshold
        self._on_update_callback = on_update_callback

        self._prompt_path = Path(prompt_path) if prompt_path else None
        self._system_prompt = self._load_prompt()
        self._prompt_mtime: float = 0.0
        if self._prompt_path and self._prompt_path.exists():
            self._prompt_mtime = self._prompt_path.stat().st_mtime

        # ---- 缓冲池管理 ----
        self._buffer_counter = 0
        self._current_buffer: Optional[_Buffer] = None   # 当前正在积累的池
        self._pending_buffers: asyncio.Queue = asyncio.Queue()  # 已提交待处理的池
        self._processed_buffers: list[_Buffer] = []       # 已处理完成的池（用于上文）
        self._lock = threading.RLock()                     # 保护 current_buffer 切换

        # ---- 异步基础设施 ----
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False

        # ---- 统计 ----
        self._stats = {"total": 0, "modified": 0, "errors": 0, "tokens": 0}

        # 初始化当前缓冲池
        self._create_new_buffer()

        self._logger.info("LLMCorrector 多缓冲池版启动: provider=%s, threshold=%s, idle_timeout=%ss",
                          self._provider, self._batch_threshold, self._idle_timeout,)

    # ── 缓冲池管理（线程安全） ────────────────────────────

    def _create_new_buffer(self) -> None:
        """创建新的当前缓冲池（加锁）"""
        with self._lock:
            self._buffer_counter += 1
            buf = _Buffer(id=self._buffer_counter)
            self._current_buffer = buf
            self._logger.debug("创建新缓冲池 id=%s", buf.id)
            # 超时由 correct() 在首次写入文本时安排

    def _get_current_buffer(self) -> _Buffer:
        """获取当前缓冲池（线程安全）"""
        with self._lock:
            return self._current_buffer

    def _swap_buffer(self, old_buffer: _Buffer) -> None:
        """提交旧池，创建新池（由 correct 或超时触发）"""
        # 先确保旧池被标记为 submitted 并放入队列
        old_buffer.status = "submitted"
        old_buffer.last_updated = time.time()
        # 取消其超时任务（如果存在）
        if old_buffer.timeout_task and not old_buffer.timeout_task.done():
            old_buffer.timeout_task.cancel()
        # 放入待处理队列
        asyncio.run_coroutine_threadsafe(
            self._pending_buffers.put(old_buffer), self._loop
        )
        self._logger.info("提交缓冲池 id=%s, 字数=%s", old_buffer.id, len(old_buffer.text))
        # 创建新池
        self._create_new_buffer()

    # ── 超时管理（异步） ──────────────────────────────────

    async def _schedule_timeout(self, buf: _Buffer) -> None:
        """为缓冲池安排一个超时任务，到期自动提交"""
        if buf.timeout_task and not buf.timeout_task.done():
            buf.timeout_task.cancel()
        # 创建新任务
        task = asyncio.create_task(self._timeout_worker(buf))
        buf.timeout_task = task
        try:
            await task
        except asyncio.CancelledError:
            self._logger.debug("缓冲池 id=%s 超时任务被取消", buf.id)

    async def _timeout_worker(self, buf: _Buffer) -> None:
        """等待 idle_timeout 秒，若期间未取消且池中有文本则提交"""
        await asyncio.sleep(self._idle_timeout)
        with self._lock:
            if (self._current_buffer is buf
                    and buf.status == "accumulating"
                    and buf.text.strip()):
                self._logger.info("缓冲池 id=%s 静默超时，自动提交", buf.id)
                self._swap_buffer(buf)
            else:
                self._logger.debug("缓冲池 id=%s 已非当前池或已提交，忽略超时", buf.id)

    # ── 生命周期 ────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        if not self._api_key:
            self._logger.warning("LLMCorrector 未配置 api_key，跳过启动")
            return

        self._running = True
        self._logger.info("LLMCorrector Worker 启动中...")
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
        while self._loop is None:
            time.sleep(0.001)
        self._logger.info("LLMCorrector Worker 已启动")

    def _run_event_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._worker_loop())

    def stop(self) -> None:
        if not self._running:
            return
        # 先提交当前池（强制）
        self.flush()
        self._running = False
        self._logger.info("LLMCorrector Worker 停止中...")
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._loop = None
        self._thread = None
        self._logger.info("LLMCorrector Worker 已停止")

    # ── 纠错入口（同步，非阻塞） ─────────────────────────

    def correct(self, sentence: Sentence) -> Sentence:
        """累积句子到当前缓冲池，触发条件时自动提交"""
        if not sentence.text.strip() or not self._api_key:
            return sentence

        buf = self._get_current_buffer()
        # 追加文本（加句号保证断句）
        buf.text += sentence.text.strip() + "。"
        buf.sentences.append(sentence)
        buf.last_updated = time.time()

        # 重置超时任务（取消旧任务，创建新任务）
        if self._loop and self._running:
            asyncio.run_coroutine_threadsafe(
                self._schedule_timeout(buf), self._loop
            )

        # 检查是否达到字数阈值
        if len(buf.text) >= self._batch_threshold:
            self._logger.debug("缓冲池 id=%s 达到字数阈值，提交", buf.id)
            with self._lock:
                if self._current_buffer is buf and buf.status == "accumulating":
                    self._swap_buffer(buf)

        return sentence

    # ── 强制刷新 ──────────────────────────────────────────

    def flush(self) -> None:
        """立即提交当前缓冲池（即使不足阈值）"""
        buf = self._get_current_buffer()
        if buf and buf.text and buf.status == "accumulating":
            with self._lock:
                if self._current_buffer is buf:
                    self._logger.info("强制提交缓冲池 id=%s", buf.id)
                    self._swap_buffer(buf)

    # ── 后台工作者循环 ──────────────────────────────────────

    async def _worker_loop(self) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while self._running:
                try:
                    buf = await asyncio.wait_for(
                        self._pending_buffers.get(), timeout=0.1
                    )
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

                try:
                    await self._process_buffer(client, buf)
                except Exception as e:
                    self._logger.exception("处理缓冲池 id=%s 失败: %s", buf.id, e)
                    self._stats["errors"] += 1
                self._pending_buffers.task_done()

    async def _process_buffer(self, client: httpx.AsyncClient, buf: _Buffer) -> None:
        """处理单个缓冲池：调用 LLM，设置修正结果，回调"""
        start_time = time.perf_counter()

        # 获取上文：取最近几个已处理完的池的修正结果
        context_text = ""
        if self._processed_buffers:
            # 取最多 max_context_buffers 个已处理池的修正结果拼接
            recent = self._processed_buffers[-self._max_context_buffers:]
            context_text = " ".join([b.corrected_text or b.text for b in recent])

        # 调用 LLM
        corrected, summary = await self._call_llm_batch_with_retry(
            client, buf.text, context_text
        )

        latency = (time.perf_counter() - start_time) * 1000

        if corrected is not None and corrected != buf.text:
            buf.corrected_text = corrected
            buf.summary = summary
            buf.status = "done"
            self._processed_buffers.append(buf)
            if len(self._processed_buffers) > self._max_context_buffers * 2:
                self._processed_buffers = self._processed_buffers[-self._max_context_buffers:]

            self._stats["modified"] += 1
            self._logger.info(
                "缓冲池 id=%s 修正成功: 原长=%s, 修正长=%s, 耗时=%.0fms",
                buf.id, len(buf.text), len(corrected), latency
            )
            if summary:
                self._logger.info("段落总结: %s", summary)

            # 回调：将修正段落作为一个独立的新 Sentence 发出，不破坏原始句子
            if buf.sentences and self._on_update_callback:
                merged = Sentence(
                    raw_text=buf.text,
                    text=corrected,
                    is_final=True,
                    llm_corrected=True,
                    batch_summary=summary,
                    start_time=buf.sentences[0].start_time,
                    end_time=buf.sentences[-1].end_time,
                )
                self._on_update_callback(merged)
        else:
            self._logger.debug("缓冲池 id=%s 修正无变化或失败", buf.id)
        self._stats["total"] += 1

    # ── LLM 调用（与之前类似，但改为接收文本） ────────────

    async def _call_llm_batch_with_retry(
        self, client: httpx.AsyncClient, raw_text: str, context_text: str
    ) -> tuple[Optional[str], Optional[str]]:
        """带重试的 LLM 调用，返回 (修正段落, 总结)"""
        last_exception = None
        base_delay = 1.0
        for attempt in range(self._max_retries + 1):
            try:
                return await self._call_llm_batch_once(client, raw_text, context_text)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (400, 401, 403, 413, 422):
                    self._logger.warning("不可重试错误 %s: %s", status, e.response.text)
                    return None, None
                if status == 429 or status >= 500:
                    delay = base_delay * (2 ** attempt) + 0.1
                    self._logger.warning(
                        "请求失败 %s，%.1fs 后重试 (attempt %s/%s)",
                        status, delay, attempt + 1, self._max_retries + 1
                    )
                    await asyncio.sleep(delay)
                    last_exception = e
                    continue
                self._logger.error("未预期的 HTTP 错误: %s", e.response.text)
                return None, None
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                delay = base_delay * (2 ** attempt) + 0.1
                self._logger.warning(
                    "网络超时，%.1fs 后重试 (attempt %s/%s)",
                    delay, attempt + 1, self._max_retries + 1
                )
                await asyncio.sleep(delay)
                last_exception = e
                continue
        self._logger.error("重试全部失败: %s", last_exception)
        return None, None

    async def _call_llm_batch_once(
        self, client: httpx.AsyncClient, raw_text: str, context_text: str
    ) -> tuple[Optional[str], Optional[str]]:
        self._reload_prompt_if_changed()

        user_content = f"上文（仅供参考）：{context_text}\n\n待修正文本：{raw_text}" if context_text else f"待修正文本：{raw_text}"

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1024,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        resp = await client.post(self._base_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {})
        self._stats["tokens"] += usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)

        content = data["choices"][0]["message"]["content"].strip()
        article, summary = self._parse_batch_response(content)
        if article is not None:
            return article, summary
        # 容错
        self._logger.warning("未检测到标准标记，将整个响应作为修正段落")
        return content, None

    def _parse_batch_response(self, content: str) -> tuple[Optional[str], Optional[str]]:
        article_marker = "[修正段落]"
        summary_marker = "[段落总结]"
        article, summary = None, None
        if article_marker in content:
            idx_article = content.find(article_marker)
            rest = content[idx_article + len(article_marker):].strip()
            if summary_marker in rest:
                idx_summary = rest.find(summary_marker)
                article = rest[:idx_summary].strip()
                summary = rest[idx_summary + len(summary_marker):].strip()
            else:
                article = rest.strip()
        return article, summary

    # ── Prompt 管理（同前） ──────────────────────────────

    def _load_prompt(self) -> str:
        if not self._prompt_path or not self._prompt_path.exists():
            return _DEFAULT_SYSTEM_PROMPT
        try:
            import yaml
            with open(self._prompt_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("system_prompt", _DEFAULT_SYSTEM_PROMPT)
        except Exception as e:
            self._logger.warning("加载 Prompt 失败: %s，使用默认值", e)
            return _DEFAULT_SYSTEM_PROMPT

    def _reload_prompt_if_changed(self) -> None:
        if not self._prompt_path or not self._prompt_path.exists():
            return
        try:
            mtime = self._prompt_path.stat().st_mtime
            if mtime > self._prompt_mtime:
                self._system_prompt = self._load_prompt()
                self._prompt_mtime = mtime
                self._logger.info("Prompt 已热更新")
        except Exception as e:
            self._logger.warning("检查 Prompt 更新失败: %s", e)

    # ── 工具方法 ──────────────────────────────────────────

    def get_stats(self) -> dict[str, int]:
        return self._stats.copy()

    @property
    def stats(self) -> dict[str, int]:
        return self._stats
