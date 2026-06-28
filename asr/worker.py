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
from corrector.base import BaseCorrector


class ASRWorker:
    """
    ASR 工作线程。

    负责协调各模块完成语音识别流程。
    """

    def __init__(
        self,
        buffer: RingBuffer[np.ndarray],
        recognizer: BaseRecognizer,
        corrector: BaseCorrector,
        event_bus: EventBus,
    ) -> None:

        self._logger = get_logger()

        self._buffer = buffer
        self._recognizer = recognizer
        self._corrector = corrector
        self._event_bus = event_bus

        self._thread: Thread | None = None
        self._running = False

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

            sentence = self._recognizer.recognize()
            sentence = self._corrector.correct(sentence)

            if not sentence.text.strip():
                continue

            if not sentence.is_final:
                continue

            self._event_bus.emit(Event(Events.SENTENCE, sentence))
