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

    # ── 音频 ──
    sample_rate: int = 16000
    channels: int = 1
    block_size: int = 1600    # 100ms 一帧

    # ── 语音识别 ──
    model_dir: str = r"C:\Users\21592\.cache\modelscope\hub\models\damo\SenseVoiceSmall"
    device: str = "cpu"

    # ── Worker 调度 ──
    recognize_window: float = 4.0      # 每次送入识别的音频长度（秒）
    overlap_window: float = 1.0        # 重叠窗口长度（秒），防止切句
    enable_vad: bool = False           # 是否启用语音活动检测（预留）
