"""
语音识别器实现。

第一版使用 FakeRecognizer 联调，后续替换为 SenseVoice。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import re
from funasr import AutoModel

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


class SenseVoiceRecognizer(BaseRecognizer):
    """
    SenseVoice 语音识别器。
    """

    def __init__(
        self,
        model_dir: str | Path,
        device: str = "cpu",
    ) -> None:

        self._logger = get_logger()

        self._model_dir = model_dir
        self._device = device

        self._model: AutoModel | None = None

    def load_model(self) -> None:
        """
        加载 SenseVoice 模型。
        """

        self._logger.info("Loading SenseVoice model...")

        self._model = AutoModel(
            model=str(self._model_dir),
            device=self._device,
            disable_update=True,
        )

        self._logger.info("SenseVoice model loaded.")

    @staticmethod
    def _clean_text(text: str) -> str:
        """去除 SenseVoice 标签（语言、情感、事件等）。"""
        return re.sub(r"<\|.*?\|>", "", text).strip()

    def recognize(
        self,
        audio: np.ndarray,
    ) -> Sentence:
        """
        语音识别。
        """

        assert self._model is not None

        # (1600, 1) -> (1600,)
        if audio.ndim == 2:
            audio = audio.squeeze(axis=1)

        result = self._model.generate(
            input=audio,
            disable_pbar=True,
        )

        text = result[0]["text"]
        text = self._clean_text(text)

        return Sentence(
            raw_text=text,
            text=text,
            is_final=True,
            confidence=1.0,
        )

    def release(self) -> None:
        """
        释放模型资源。
        """

        self._model = None

        self._logger.info("SenseVoice model released.")






