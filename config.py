"""
SpeechNote 全局配置。

所有配置统一放在此处，业务模块只读取配置，
不得在运行过程中修改配置对象。
"""

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Config:
    """应用程序配置。"""

    app_name: str = "SpeechNote"

    version: str = "0.1.0"

    sample_rate: int = 16000

    channels: int = 1

    block_size: int = 1600    #100ms 一帧。