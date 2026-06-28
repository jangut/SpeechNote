"""
文本纠错器抽象接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.sentence import Sentence


class BaseCorrector(ABC):
    """
    文本纠错器抽象基类。

    所有纠错器都应继承该类。
    """

    @abstractmethod
    def correct(self, sentence: Sentence) -> Sentence:
        """
        对 Sentence 进行纠错。

        Parameters
        ----------
        sentence
            待处理文本。

        Returns
        -------
        Sentence
            纠错后的文本。
        """
        raise NotImplementedError