"""
默认纠错器。

不对文本进行任何修改。
"""

from __future__ import annotations

from core.sentence import Sentence
from corrector.base import BaseCorrector


class IdentityCorrector(BaseCorrector):
    """
    默认纠错器。

    第一版直接返回原 Sentence，
    用于预留后续 AI、词典等纠错能力。
    """

    def correct(self, sentence: Sentence) -> Sentence:
        """
        不进行任何修改。

        Parameters
        ----------
        sentence
            待处理文本。

        Returns
        -------
        Sentence
            原始 Sentence。
        """
        return sentence