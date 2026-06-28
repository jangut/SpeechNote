"""
SpeechNote 统一文本数据模型。

整个工程统一传递 Sentence，
禁止直接传递字符串。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid4


class SourceType(StrEnum):
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
    """

    id: UUID = field(default_factory=uuid4)

    raw_text: str = ""

    text: str = ""

    start_time: float = 0.0

    end_time: float = 0.0

    source: SourceType = SourceType.MICROPHONE

    confidence: float | None = None

    is_final: bool = False

    def __post_init__(self) -> None:
        """
        如果未指定 text，
        默认与 raw_text 保持一致。
        """
        if not self.text:
            self.text = self.raw_text