"""
SpeechNote 统一文本数据模型。

整个工程统一传递 Sentence，
禁止直接传递字符串。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID, uuid4


class SourceType(str, Enum):
    """语音来源。"""

    MICROPHONE = "microphone"
    SYSTEM = "system"
    FILE = "file"


@dataclass(slots=True)
class Sentence:
    """
    统一文本数据对象。

    Attributes
    ----------
    id
        唯一标识。
    raw_text
        ASR 原始输出，永不修改。
    text
        当前文本，可被纠错器修改。
    start_time
        开始时间（秒）。
    end_time
        结束时间（秒）。
    source
        音频来源。
    confidence
        识别置信度。
    is_final
        是否最终结果。
    llm_corrected
        是否已被 LLM 修正（用于区分 pre/post LLM 导出）。
    batch_summary
        LLM 批量纠错的段落总结（可选）。
    """

    id: UUID = field(default_factory=uuid4)
    raw_text: str = ""
    text: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    source: SourceType = SourceType.MICROPHONE
    confidence: float | None = None
    is_final: bool = False
    llm_corrected: bool = False
    batch_summary: str | None = None

    def __post_init__(self) -> None:
        if not self.text:
            self.text = self.raw_text
