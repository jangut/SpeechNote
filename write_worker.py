"""
ASR 工作线程。

负责调度整个语音识别流水线：

RingBuffer
    ↓
Recognizer
    ↓
Corrector
    ↓
EventBus
"""

from __future__ import annotations

from threading import Thread

import numpy as np

from audio.ringbuffer import RingBuffer
from asr.base import BaseRecognizer
from core.event import Event, EventBus
from core.events import Events
from core.logger import get_logger
from corrector.pipeline import CorrectorPipeline


class ASRWorker:
    """
    ASR 工作线程。

    负责协调各模块完成语音识别流程。
    """

    def __init__(
        self,
        buffer: RingBuffer[np.ndarray],
        recognizer: BaseRecognizer,
        pipeline: CorrectorPipeline,
        event_bus: EventBus,
        *,
        sample_rate: int,
        recognize_window: float,
        overlap_window: float = 0.0,
        enable_vad: bool = False,
    ) -> None:

        self._logger = get_logger()

        self._buffer = buffer
        self._recognizer = recognizer
        self._pipeline = pipeline
        self._event_bus = event_bus

        self._thread: Thread | None = None
        self._running = False

        self._sample_rate = sample_rate
        self._required_samples = int(sample_rate * recognize_window)
        self._overlap_samples = int(sample_rate * overlap_window) if overlap_window > 0 else 0
        self._enable_vad = enable_vad

        self._audio_cache: list[np.ndarray] = []
        self._cached_samples = 0

    def start(self) -> None:
        """启动工作线程。"""
        self._running = True
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()
        self._logger.info("ASRWorker started.")

    def stop(self) -> None:
        """停止工作线程。"""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._logger.info("ASRWorker stopped.")

    def _run(self) -> None:
        """工作线程主循环。"""
        while self._running:
            try:
                audio_data = self._buffer.pop(block=True, timeout=1.0)
            except Exception:
                continue

            # VAD（预留）
            if self._enable_vad:
                pass

            self._audio_cache.append(audio_data)
            self._cached_samples += len(audio_data)

            if self._cached_samples < self._required_samples:
                continue

            audio = np.concatenate(self._audio_cache, axis=0)

            # 重叠窗口：保留最后一段供下一轮拼接
            if self._overlap_samples > 0:
                keep = audio[-self._overlap_samples:]
                self._audio_cache = [keep]
                self._cached_samples = len(keep)
            else:
                self._audio_cache.clear()
                self._cached_samples = 0

            self._logger.info(
                "Recognize %.2fs audio, shape=%s",
                len(audio) / self._sample_rate,
                audio.shape,
            )

            try:
                sentence = self._recognizer.recognize(audio)
                sentence = self._pipeline.correct(sentence)
            except Exception:
                self._logger.exception("Recognition failed")
                self._event_bus.emit(Event(Events.ERROR, None))
                continue

            if not sentence.text.strip():
                continue

            if not sentence.is_final:
                continue

            self._event_bus.emit(Event(Events.SENTENCE, sentence))


