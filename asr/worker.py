"""
ASR 工作线程。

负责调度整个语音识别流水线：

RingBuffer
    ↓
Recognizer
    ↓
Pipeline
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
    """

    def __init__(
        self,
        buffer: RingBuffer[np.ndarray],
        recognizer: BaseRecognizer,
        pipeline: CorrectorPipeline,
        event_bus: EventBus,
        *,
        mode: str = "vad",
        sample_rate: int,
        recognize_window: float,
        overlap_window: float = 0.0,
        enable_vad: bool = False,
        vad_threshold: float = 0.005,
        silence_timeout: float = 0.5,
    ) -> None:

        self._logger = get_logger()

        self._buffer = buffer
        self._recognizer = recognizer
        self._pipeline = pipeline
        self._event_bus = event_bus

        self._thread: Thread | None = None
        self._running = False

        # -- audio --
        self._sample_rate = sample_rate
        self._required_samples = int(sample_rate * recognize_window)
        self._overlap_samples = int(sample_rate * overlap_window) if overlap_window > 0 else 0

        # -- mode --
        self._mode = mode
        self._use_vad_early_flush = (mode == "vad")

        # -- VAD --
        self._enable_vad = enable_vad
        self._vad_threshold = vad_threshold
        self._silence_chunks = max(1, int(silence_timeout * sample_rate / 1600))
        self._min_samples = int(sample_rate * 1.0)
        self._speech_active = False
        self._silence_counter = 0

        # -- cache --
        self._audio_cache: list[np.ndarray] = []
        self._cached_samples = 0

    def start(self) -> None:
        self._running = True
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()
        self._logger.info("ASRWorker started.")

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._logger.info("ASRWorker stopped.")

    def _is_speech(self, audio: np.ndarray) -> bool:
        rms = np.sqrt(np.mean(audio ** 2))
        return rms > self._vad_threshold

    def _flush_audio(self, keep_overlap: bool = True) -> None:
        if self._cached_samples == 0:
            return

        audio = np.concatenate(self._audio_cache, axis=0)

        if keep_overlap and self._overlap_samples > 0:
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
            return

        if not sentence.text.strip():
            return
        if not sentence.is_final:
            return

        self._event_bus.emit(Event(Events.SENTENCE, sentence))

    def _run(self) -> None:
        while self._running:
            try:
                audio_data = self._buffer.pop(block=True, timeout=1.0)
            except Exception:
                continue

            # -- VAD --
            if self._enable_vad:
                if not self._is_speech(audio_data):
                    if not self._speech_active:
                        continue
                    self._silence_counter += 1
                    if self._silence_counter >= self._silence_chunks:
                        if self._cached_samples >= self._min_samples:
                            self._flush_audio(keep_overlap=False)
                        self._speech_active = False
                        self._silence_counter = 0
                        self._audio_cache.clear()
                        self._cached_samples = 0
                        continue
                else:
                    self._silence_counter = 0
                    if not self._speech_active:
                        self._speech_active = True
                        self._audio_cache.clear()
                        self._cached_samples = 0

            # -- cache --
            self._audio_cache.append(audio_data)
            self._cached_samples += len(audio_data)

            # -- max window --
            if self._cached_samples >= self._required_samples:
                self._flush_audio(keep_overlap=self._speech_active)
