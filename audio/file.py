"""
文件音频读取器，模拟实时音频流推入 Buffer。
"""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np
import soundfile as sf

from audio.base import BaseRecorder
from audio.ringbuffer import RingBuffer
from core.logger import get_logger


class FileRecorder(BaseRecorder):
    """
    从本地音频文件读取数据，模拟实时音频流推入 RingBuffer。
    """

    def __init__(
        self,
        buffer: RingBuffer[np.ndarray],
        file_path: str,
        sample_rate: int,
        channels: int,
        block_size: int,
        loop: bool = False,  # 是否循环播放，测试时常用
    ) -> None:
        self._logger = get_logger()

        self._buffer = buffer
        self._file_path = file_path
        self._sample_rate = sample_rate
        self._channels = channels
        self._block_size = block_size
        self._loop = loop

        self._thread: threading.Thread | None = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """
        当前是否正在读取。
        """
        return self._is_running

    def _run(self) -> None:
        """
        线程执行函数：模拟实时读取音频文件。
        """
        try:
            # 这里不指定 samplerate 和 channels，读取文件原始属性
            # 如果文件采样率和目标采样率不一致，ASR前可能需要重采样，这里假设一致或由下游处理
            audio_data, sr = sf.read(self._file_path, dtype="float32")
            
            # 如果音频是单声道，但系统配置要求多声道，进行扩展 (简单处理)
            if len(audio_data.shape) == 1 and self._channels > 1:
                audio_data = np.column_stack([audio_data] * self._channels)
            elif len(audio_data.shape) > 1 and self._channels == 1:
                # 如果是多声道但要求单声道，取平均值
                audio_data = np.mean(audio_data, axis=1, keepdims=True)

        except Exception as e:
            self._logger.error(f"Failed to load audio file {self._file_path}: {e}")
            self._is_running = False
            return

        self._logger.info(f"File audio loaded. SR: {sr}, Shape: {audio_data.shape}")

        # 计算每个 block 需要休眠的时间，模拟真实音频流
        sleep_time = self._block_size / self._sample_rate

        while self._is_running:
            num_frames = len(audio_data)
            for i in range(0, num_frames, self._block_size):
                if not self._is_running:
                    break

                chunk = audio_data[i:i + self._block_size]
                
                # 如果最后一块不足 block_size，补零或跳过（这里选择补零保证长度一致）
                if len(chunk) < self._block_size:
                    pad_shape = (self._block_size - len(chunk), self._channels) if self._channels > 1 else (self._block_size - len(chunk),)
                    chunk = np.pad(chunk, ( (0, pad_shape[0]), ) + ((0,0),) if self._channels > 1 else ((0,0),), 'constant')
                    # 推入并退出本轮
                    self._buffer.push(chunk.astype(np.float32, copy=True))
                    break

                self._buffer.push(chunk.astype(np.float32, copy=True))
                
                # 模拟实时播放的速度
                time.sleep(sleep_time)

            if not self._loop:
                self._logger.info("File audio reading finished.")
                break
            else:
                self._logger.info("File audio looping...")

        self._is_running = False

    def start(self) -> None:
        """
        开始读取文件。
        """
        if self._is_running:
            return

        self._is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

        self._logger.info("File audio reader started.")

    def stop(self) -> None:
        """
        停止读取文件。
        """
        if not self._is_running:
            return

        self._is_running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        self._logger.info("File audio reader stopped.")
