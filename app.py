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

from core.event import Event, EventBus
from core.events import Events
from core.logger import configure_logger, get_logger

from audio.ringbuffer import RingBuffer
from audio.base import BaseRecorder
from audio.mic import MicrophoneRecorder
from audio.system import SystemAudioRecorder
from audio.file import FileRecorder

from asr.base import BaseRecognizer
from asr.recognizer import SenseVoiceRecognizer
from asr.worker import ASRWorker

from corrector.pipeline import CorrectorPipeline
from corrector.duplicate import DuplicateCorrector
from corrector.identity import TermCorrector
from corrector.llm_corrector import LLMCorrector

from plugins.base import BasePlugin
from plugins.markdown import MarkdownPlugin


class Application:
    """SpeechNote 应用程序。"""

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or Config()

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


        self._llm_corrector = LLMCorrector(
            base_url=self._config.llm_base_url,
            api_key=self._config.llm_api_key,
            model=self._config.llm_model,
            provider=self._config.llm_provider,
            timeout=self._config.llm_timeout,
            max_retries=self._config.llm_max_retries,
            max_context_sentences=self._config.llm_max_context_sentences,
            idle_timeout=self._config.llm_idle_timeout,
            short_text_threshold=self._config.llm_short_text_threshold,
            prompt_path=self._config.llm_prompt_file or None,
            on_update_callback=self._on_llm_correction,
        )
        self._pipeline = CorrectorPipeline([
            DuplicateCorrector(),
            TermCorrector(),
            self._llm_corrector,
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

    @property
    def event_bus(self) -> EventBus:
        """Get EventBus instance."""
        assert self._event_bus is not None
        return self._event_bus

    def start(self) -> None:
        """启动应用程序。"""

        assert self._recognizer is not None
        assert self._worker is not None
        assert self._recorder is not None

        self._event_bus.emit(Event(Events.START, None))

        self._recognizer.load_model()

        for plugin in self._plugins:
            plugin.start()

        self._worker.start()

        self._recorder.start()
        self._llm_corrector.start()

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

        if self._llm_corrector:
            self._llm_corrector.stop()

        for plugin in self._plugins:
            plugin.stop()

        if self._recognizer:
            self._recognizer.release()

        self._event_bus.emit(Event(Events.STOP, None))

        self._logger.info(
            "SpeechNote exited."
        )

    def _on_llm_correction(self, sentence: Sentence) -> None:
        """LLM 修正完成后的回调，重新发射 SENTENCE 事件。"""
        self._event_bus.emit(Event(Events.SENTENCE, sentence))

    def _create_recorder(self, source_type: str | None = None, file_path: str = "") -> BaseRecorder:
        """根据配置创建对应的录音器。"""
        source = source_type if source_type is not None else self._config.audio_source
        if source == "system":
            return SystemAudioRecorder(
                buffer=self._buffer,
                sample_rate=self._config.sample_rate,
                channels=self._config.channels,
                block_size=self._config.block_size,
            )
        elif source == "file":
            return FileRecorder(
                buffer=self._buffer,
                file_path=file_path or self._config.audio_file_path,
                sample_rate=self._config.sample_rate,
                channels=self._config.channels,
                block_size=self._config.block_size,
            )
        else:
            return MicrophoneRecorder(
                buffer=self._buffer,
                sample_rate=self._config.sample_rate,
                channels=self._config.channels,
                block_size=self._config.block_size,
            )

    def switch_audio_source(self, source_type: str, file_path: str = "") -> None:
        """运行时切换音频来源，不重启整个管线。"""
        if self._recorder:
            self._recorder.stop()
        if source_type == "file" and not file_path:
            self._logger.warning("切换到文件来源但未指定文件路径")
            return
        self._recorder = self._create_recorder(source_type=source_type, file_path=file_path)
        self._recorder.start()
        self._logger.info("音频来源已切换为: %s", source_type)

    def run(self) -> None:
        """运行应用程序。"""
        self.initialize()
        self.start()
        self.wait()








