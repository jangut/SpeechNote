"""
文本纠错模块。
"""

from corrector.base import Corrector
from corrector.identity import IdentityCorrector

__all__ = [
    "Corrector",
    "IdentityCorrector",
]