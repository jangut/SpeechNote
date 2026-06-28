"""
语音识别器抽象接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.sentence import Sentence


class BaseRecognizer(ABC):
    """
    语音识别器抽象基类。
    """

    @abstractmethod
    def load_model(self) -> None:
        """
        加载模型。
        """
        raise NotImplementedError

    @abstractmethod
    def recognize(self) -> Sentence:
        """
        执行一次识别。

        Returns
        -------
        Sentence
            识别结果。
        """
        raise NotImplementedError

    @abstractmethod
    def release(self) -> None:
        """
        释放资源。
        """
        raise NotImplementedError