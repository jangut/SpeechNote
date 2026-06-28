"""
应用程序入口。

Application 是整个工程唯一知道所有对象的人，
负责对象创建、依赖注入、生命周期管理。

禁止在此编写业务逻辑。
"""

from __future__ import annotations

import time

import numpy as np

from config import Config

from core.event import EventBus
from core.logger import configure_logger, get_logger

from audio.ringbuffer import RingBuffer
from audio.base import BaseRecorder
from audio.recorder import MicrophoneRecorder

from asr.base import BaseRecognizer
from asr.recognizer import SenseVoiceRecognizer
from asr.worker import ASRWorker

from corrector.pipeline import CorrectorPipeline
from corrector.duplicate import DuplicateCorrector

from plugins.base import BasePlugin
from plugins.markdown import MarkdownPlugin


class Application:
    """SpeechNote 应用程序。"""

    def __init__(self) -> None:
        self._config = Config()

        configure_logger()
        self._logger = get_logger()

        self._event_bus: EventBus | None = None

        self._buffer: RingBuffer[np.ndarray] | None = None

        self._recognizer: BaseRecognizer | None = None

        self._corrector: BaseCorrector | None = None

        self._worker: ASRWorker | None = None

        self._recorder: BaseRecorder | None = None

        self._plugins: list[BasePlugin] = []

    def initialize(self) -> None:
        """初始化应用程序。"""

        configure_logger()

        self._logger.info(
            "%s v%s initializing...",
            self._config.app_name,
            self._config.version,
        )

        self._event_bus = EventBus()

        self._buffer = RingBuffer[np.ndarray]()

        self._recognizer = SenseVoiceRecognizer(model_dir=self._config.model_dir, device=self._config.device)

        self._pipeline = CorrectorPipeline([
            DuplicateCorrector(),
        ])

        self._worker = ASRWorker(
            buffer=self._buffer,
            recognizer=self._recognizer,
            pipeline=self._pipeline,
            event_bus=self._event_bus,
            mode=self._config.mode,
            sample_rate=self._config.sample_rate,
            recognize_window=self._config.recognize_window,
            overlap_window=self._config.overlap_window,
            enable_vad=self._config.enable_vad,
            vad_threshold=self._config.vad_threshold,
            silence_timeout=self._config.silence_timeout,
        )

        self._recorder = MicrophoneRecorder(
            buffer=self._buffer,
            sample_rate=self._config.sample_rate,
            channels=self._config.channels,
            block_size=self._config.block_size,
        )

        self._plugins = [
            MarkdownPlugin(output_dir="notes"),
        ]

        for plugin in self._plugins:
            plugin.register(self._event_bus)

    def start(self) -> None:
        """启动应用程序。"""

        assert self._recognizer is not None
        assert self._worker is not None
        assert self._recorder is not None

        self._recognizer.load_model()

        for plugin in self._plugins:
            plugin.start()

        self._worker.start()

        self._recorder.start()

        self._logger.info("Application started.")

    def wait(self) -> None:
        """等待程序结束。"""

        try:
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """停止应用程序。"""

        if self._recorder:
            self._recorder.stop()

        if self._worker:
            self._worker.stop()

        for plugin in self._plugins:
            plugin.stop()

        if self._recognizer:
            self._recognizer.release()

        self._logger.info(
            "SpeechNote exited."
        )

    def run(self) -> None:
        """运行应用程序。"""
        self.initialize()
        self.start()
        self.wait()






