"""
麦克风录音器。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import sounddevice as sd

from audio.base import BaseRecorder
from audio.ringbuffer import RingBuffer
from core.logger import get_logger


class MicrophoneRecorder(BaseRecorder):
    """
    基于 sounddevice 的麦克风录音器。
    """

    def __init__(
        self,
        buffer: RingBuffer[np.ndarray],
        sample_rate: int,
        channels: int,
        block_size: int,
    ) -> None:
        self._logger = get_logger()

        self._buffer = buffer

        self._sample_rate = sample_rate
        self._channels = channels
        self._block_size = block_size

        self._stream: sd.InputStream | None = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """
        当前是否正在录音。
        """
        return self._is_running

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time: Any,
        status: sd.CallbackFlags,
    ) -> None:
        """
        音频采集回调函数。
        """

        if status:
            self._logger.warning(status)

        # sounddevice 官方建议复制数据
        self._buffer.push(indata.astype(np.float32, copy=True))

    def start(self) -> None:
        """
        开始录音。
        """

        if self._is_running:
            return

        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            blocksize=self._block_size,
            callback=self._callback,
        )

        self._stream.start()

        self._is_running = True

        self._logger.info("Microphone recorder started.")

    def stop(self) -> None:
        """
        停止录音。
        """

        if not self._is_running:
            return

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        self._is_running = False

        self._logger.info("Microphone recorder stopped.")