"""
Fake 语音识别器。

第一版用于联调，后续替换为 SenseVoice。
"""

from __future__ import annotations

from core.logger import get_logger
from core.sentence import Sentence
from asr.base import BaseRecognizer


class FakeRecognizer(BaseRecognizer):
    """
    Fake 语音识别器。

    固定返回 "你好，世界"。
    """

    def __init__(self) -> None:
        self._logger = get_logger()
        self._loaded = False

    def load_model(self) -> None:
        """
        加载模型。
        """
        self._loaded = True
        self._logger.info("FakeRecognizer model loaded.")

    def recognize(self) -> Sentence:
        """
        执行一次识别。

        Returns
        -------
        Sentence
            固定返回 "你好，世界"。
        """
        return Sentence(
            raw_text="你好，世界",
            text="你好，世界",
            is_final=True,
        )

    def release(self) -> None:
        """
        释放资源。
        """
        self._loaded = False
        self._logger.info("FakeRecognizer released.")
