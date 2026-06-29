"""
文本纠错模块。
"""

from corrector.base import BaseCorrector
from corrector.identity import TermCorrector
from corrector.duplicate import DuplicateCorrector
from corrector.pipeline import CorrectorPipeline
