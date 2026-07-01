"""
SpeechNote 全局配置。

所有配置统一放在此处，业务模块只读取配置，
不得在运行过程中修改配置对象。
"""

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Config:
    """应用程序配置。"""

    # ── 基本信息 ──
    app_name: str = "SpeechNote"      # 应用名称，用于日志/UI 显示
    version: str = "1.2.0"           # 当前版本号

    # ── 音频采集参数 ──
    sample_rate: int = 16000          # 采样率（Hz），ASR 模型通常要求 16kHz
    channels: int = 1                 # 单声道，麦克风输入通常为单声道
    block_size: int = 1600            # 每次读取的音频帧大小（样本数），对应 100ms（16000*0.1）
    audio_source: str = "microphone"  # 音频来源："microphone" | "system" | "file"
    audio_file_path: str = ""         # 音频文件路径（仅在 audio_source="file" 时有效）

    # ── 语音识别（ASR）参数 ──
    model_dir: str = "damo/SenseVoiceSmall"
                                      # Paraformer 中文模型，也可换为其他 ModelScope 模型
    device: str = "cpu"               # 推理设备：'cpu' 或 'cuda'（若 GPU 可用推荐 'cuda'）

    # ── Worker 调度与 VAD 参数 ──
    mode: str = "vad"                 # 识别模式："window"（滑动窗口） | "vad"（语音活动检测）
    recognize_window: float = 8.0     # 每次送入识别的音频长度（秒），仅在 window 模式下生效
    overlap_window: float = 1.0       # 重叠窗口长度（秒），防止切句时丢失上下文
    vad_threshold: float = 0.005      # VAD 能量阈值，低于此值视为静音（需根据麦克风灵敏度微调）
    silence_timeout: float = 1.0      # 沉默超时（秒），检测到连续静音超过此值即触发识别
    enable_vad: bool = True           # 是否启用 VAD，若 False 则使用固定窗口切分

    # ── 大模型纠错（LLM）参数 ──
    # 本套配置专为本地部署的 Qwen-8B 模型（通过 Ollama）优化
    llm_provider: str = "ollama"      # 服务提供商：'ollama'（本地）、'openai'、'qwen'、'glm'、'deepseek'
    llm_base_url: str = "http://localhost:11434/v1/chat/completions"
                                      # API 端点，Ollama 默认地址，若用 vLLM 则改为相应地址
    llm_api_key: str = "ollama"       # 本地服务可不填真实 Key，但须非空（代码会校验）
    llm_model: str = "qwen3:8b"       # 模型名称，请与 `ollama list` 中的标签一致（如 qwen2.5:7b）

    llm_timeout: float = 15.0         # 单次请求超时（秒），8B 模型在 CPU 上推理较慢，适当放宽
    llm_max_retries: int = 2          # 请求失败最大重试次数（指数退避）
    llm_max_context_sentences: int = 3  # 纠错时携带的历史句子数量，用于指代消解
    llm_idle_timeout: float = 0.6     # 静音超时触发纠错（秒），缩短可提升响应速度，但增加请求频率
    llm_short_text_threshold: int = 2 # 短文本（字数 ≤ 此值）立即触发纠错，不等待静音
    llm_prompt_file: str = ""          # 自定义 Prompt YAML 文件路径，为空使用内置默认 Prompt
