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
from core.event import EventBus
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