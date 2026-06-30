"""
基于大模型的文本纠错器（异步非阻塞版）。

correct() 立即返回不阻塞 Pipeline，
后台 Worker 在独立线程的事件循环中消费队列，
修正完成后通过回调推送结果。

参数统一由 config.py 管理，通过 app.py 注入。
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Callable

import httpx

from core.logger import get_logger
from core.sentence import Sentence
from corrector.base import BaseCorrector

# ── 默认系统 Prompt ─────────────────────────────────────────
_DEFAULT_SYSTEM_PROMPT = """\
  You are a deterministic academic meeting text corrector. Output the corrected text directly. No conversational filler, no explanation.
    [Domain Keywords]
    - Circuits: Op-amp (运算放大器), MOSFET (场效应管), Filter (滤波器).
    - Control/Sensing: PID controller (PID控制器), Sensor (传感器), Closed-loop sampling (采样闭环).
    - AI/Software: CNN (卷积神经网络), Loss function (损失函数).
    [Strict Rules]
    1. Fix ASR overlaps, repetitive words, and domain terminology errors.
    2. Add proper punctuation (commas, periods, etc.) to make it a structured text.
    3. Replace long/complex spoken mathematical formulas with $[公式]$. 
    4. Keep casual conversation unchanged. Do NOT invent or add new facts.
    5. In the very last line, output "[Modified]" if any changes were made, or "[Unchanged]" if the input was already perfect.
    [Output Format]
    [Corrected Text]
    [Status Tag]
"""

# ── Provider 默认映射 ──────────────────────────────────────
_PROVIDER_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "qwen": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
    "glm": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "ollama": "http://localhost:11434/v1/chat/completions",
}


class LLMCorrector(BaseCorrector):
    """
    基于大模型的异步非阻塞纠错器。

    correct() 立即返回不阻塞 Pipeline，
    后台 Worker 在独立线程 + 事件循环中异步消费队列。
    """

    def __init__(
        self,
        *,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        provider: str = "openai",
        timeout: float = 10.0,
        max_retries: int = 2,
        max_context_sentences: int = 3,
        idle_timeout: float = 0.8,
        short_text_threshold: int = 3,
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
        self._max_context_sentences = max_context_sentences
        self._idle_timeout = idle_timeout
        self._short_text_threshold = short_text_threshold
        self._on_update_callback = on_update_callback

        self._prompt_path = Path(prompt_path) if prompt_path else None
        self._system_prompt = self._load_prompt()
        self._prompt_mtime: float = 0.0
        if self._prompt_path and self._prompt_path.exists():
            self._prompt_mtime = self._prompt_path.stat().st_mtime

        self._queue: asyncio.Queue = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._context: list[Sentence] = []
        self._sequence = 0
        self._stats = {"total": 0, "modified": 0, "errors": 0, "tokens": 0}

        self._logger.info(
            "LLMCorrector 已创建: provider=%s model=%s",
            self._provider, self._model or "(default)",
        )

    # ── 生命周期 ────────────────────────────────────────────

    def start(self) -> None:
        """启动后台 Worker（仅在 api_key 已配置时启动）。"""
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
        """停止后台 Worker（优雅关闭）。"""
        if not self._running:
            return
        self._running = False
        self._logger.info("LLMCorrector Worker 停止中...")
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._loop = None
        self._thread = None
        self._logger.info("LLMCorrector Worker 已停止")

    # ── 纠错入口（同步，非阻塞）────────────────────────────

    def correct(self, sentence: Sentence) -> Sentence:
        if not sentence.text.strip() or not self._api_key:
            return sentence

        self._context.append(sentence)
        if len(self._context) > self._max_context_sentences + 1:
            self._context.pop(0)

        self._sequence += 1
        seq = self._sequence
        assert self._loop is not None
        asyncio.run_coroutine_threadsafe(self._enqueue(sentence, seq), self._loop)
        return sentence

    async def _enqueue(self, sentence: Sentence, seq: int) -> None:
        if len(sentence.text) > self._short_text_threshold:
            await asyncio.sleep(self._idle_timeout)
            if seq != self._sequence:
                self._logger.debug("长文本被覆盖，丢弃: '%s'", sentence.text)
                return
        await self._queue.put((sentence, True))

    # ── 后台工作者循环 ──────────────────────────────────────

    async def _worker_loop(self) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while self._running:
                try:
                    sentence, with_context = await asyncio.wait_for(
                        self._queue.get(), timeout=0.1,
                    )
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                try:
                    await self._process_sentence(client, sentence, with_context)
                except Exception:
                    self._logger.exception("处理句子失败: %s", sentence.text)
                    self._stats["errors"] += 1
                self._queue.task_done()

    async def _process_sentence(
        self, client: httpx.AsyncClient, sentence: Sentence, with_context: bool,
    ) -> None:
        start_time = time.perf_counter()
        context_text = ""
        if with_context:
            idx = self._context.index(sentence) if sentence in self._context else -1
            if idx > 0:
                prev = self._context[max(0, idx - self._max_context_sentences): idx]
                context_text = " ".join(s.text for s in prev) + "\n"

        corrected = await self._call_llm_with_retry(client, sentence.text, context_text)
        latency = (time.perf_counter() - start_time) * 1000

        if corrected is not None and corrected != sentence.text:
            old_text = sentence.text
            sentence.text = corrected
            sentence.confidence = 1.0
            self._stats["modified"] += 1
            self._logger.info(
                "LLM 纠错: '%s' -> '%s' (latency=%.0fms, context=%s)",
                old_text, corrected, latency, bool(context_text),
            )
            if self._on_update_callback:
                self._on_update_callback(sentence)
        else:
            self._logger.debug("LLM 纠错无变化: '%s'", sentence.text)
        self._stats["total"] += 1

    # ── LLM API 调用（带指数退避重试）─────────────────────

    async def _call_llm_with_retry(
        self, client: httpx.AsyncClient, text: str, context_text: str = "",
    ) -> str | None:
        last_exception: Exception | None = None
        base_delay = 1.0
        for attempt in range(self._max_retries + 1):
            try:
                return await self._call_llm_once(client, text, context_text)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (400, 401, 403, 413, 422):
                    self._logger.warning("不可重试错误 %s: %s", status, e.response.text)
                    return None
                if status == 429 or status >= 500:
                    delay = base_delay * (2 ** attempt) + 0.1
                    self._logger.warning(
                        "请求失败 %s，%.1fs 后重试 (attempt %s/%s)",
                        status, delay, attempt + 1, self._max_retries + 1,
                    )
                    await asyncio.sleep(delay)
                    last_exception = e
                    continue
                self._logger.error("未预期的 HTTP 错误: %s", e.response.text)
                return None
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                delay = base_delay * (2 ** attempt) + 0.1
                self._logger.warning(
                    "网络超时，%.1fs 后重试 (attempt %s/%s)",
                    delay, attempt + 1, self._max_retries + 1,
                )
                await asyncio.sleep(delay)
                last_exception = e
                continue
        self._logger.error("重试全部失败: %s", last_exception)
        return None

    async def _call_llm_once(
        self, client: httpx.AsyncClient, text: str, context_text: str,
    ) -> str | None:
        self._reload_prompt_if_changed()
        user_content = f"上文：{context_text}\n当前句：{text}" if context_text else text
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]
        payload: dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 512,
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

        corrected = self._extract_plaintext(content, text)
        if corrected is not None:
            return corrected

        try:
            result = json.loads(content)
            corrected = result.get("corrected_text", "").strip()
            if not corrected:
                return None
            if not result.get("is_modified", False) or corrected == text:
                return None
            return corrected
        except json.JSONDecodeError:
            self._logger.warning("非 JSON 响应: %s", content[:100])

        if content and content != text:
            self._logger.info("非 JSON 兜底: '%s' -> '%s'", text, content)
            return content
        return None

    # ── 响应解析 ────────────────────────────────────────────

    @staticmethod
    def _extract_plaintext(content: str, original: str) -> str | None:
        """从 [Corrected Text]/[Status Tag] 格式中提取修正文本。"""
        marker = "[Corrected Text]"
        idx = content.find(marker)
        if idx == -1:
            return None
        rest = content[idx + len(marker):].strip()
        end_idx = rest.find("[Status Tag]")
        corrected = rest[:end_idx].strip() if end_idx != -1 else rest
        is_modified = "[Modified]" in content
        if not corrected or not is_modified or corrected == original:
            return None
        return corrected

    # ── Prompt 管理 ────────────────────────────────────────

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

    def flush(self) -> None:
        self._sequence += 1
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._flush_queue(), self._loop)

    async def _flush_queue(self) -> None:
        cleared = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                cleared += 1
            except asyncio.QueueEmpty:
                break
        if cleared:
            self._logger.debug("flush: 清除了 %s 个待处理项", cleared)
        self._context.clear()
        self._stats["total"] += cleared
        self._stats["errors"] += cleared

    @property
    def stats(self) -> dict[str, int]:
        return self._stats
