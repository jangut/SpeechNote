"""系统音频捕获器（VB-CABLE 虚拟声卡）。"""

from __future__ import annotations

import numpy as np
import sounddevice as sd

from audio.base import BaseRecorder
from audio.ringbuffer import RingBuffer
from core.logger import get_logger


class SystemAudioRecorder(BaseRecorder):
    """
    基于 VB-CABLE 虚拟声卡的系统音频捕获器。

    需要安装 VB-CABLE（免费虚拟音频驱动）：https://vb-audio.com/Cable/
    装好后在系统声音设置中把扬声器输出改为 "CABLE Output"，
    程序会自动检测 "CABLE Input" 设备进行捕获。
    """

    CABLE_DEVICE_KEYWORDS = ["CABLE", "VB-Audio", "VB-Audio Virtual Cable"]

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
        return self._is_running

    @staticmethod
    def find_cable_device() -> int | None:
        """搜索 VB-CABLE 输入设备。未找到返回 None。"""
        keywords = ["CABLE", "VB-Audio", "VB-Audio Virtual Cable"]
        try:
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                name = dev["name"].lower()
                if any(k.lower() in name for k in keywords):
                    if dev["max_input_channels"] > 0:
                        return i
        except Exception:
            pass
        return None

    def start(self) -> None:
        if self._is_running:
            return

        device_idx = self.find_cable_device()
        if device_idx is None:
            self._logger.error(
                "未检测到 VB-CABLE 虚拟声卡！"
                "请先安装 https://vb-audio.com/Cable/"
            )
            raise RuntimeError("VB-CABLE 未安装")

        device_name = sd.query_devices(device_idx)["name"]
        self._logger.info("检测到 VB-CABLE: [%d] %s", device_idx, device_name)

        try:
            self._stream = sd.InputStream(
                device=device_idx,
                samplerate=self._sample_rate,
                channels=self._channels,
                blocksize=self._block_size,
                callback=self._callback,
            )
            self._stream.start()
            self._is_running = True
            self._logger.info("System audio (VB-CABLE) started.")
        except Exception as e:
            self._logger.error("VB-CABLE 启动失败: %s", e)
            raise

    def _callback(
        self, indata: np.ndarray, frames: int,
        time: object, status: sd.CallbackFlags,
    ) -> None:
        if status:
            self._logger.warning("VB-CABLE 状态: %s", status)
        self._buffer.push(indata.astype(np.float32, copy=True))

    def stop(self) -> None:
        if not self._is_running:
            return
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._is_running = False
        self._logger.info("System audio recorder stopped.")
