from __future__ import annotations

import difflib
from pypinyin import lazy_pinyin

from core.sentence import Sentence
from corrector.base import BaseCorrector


class DuplicateCorrector(BaseCorrector):
    """
    智能去重纠错器（基于拼音的最长公共子串匹配）。
    
    专治流式 ASR 窗口重叠导致的文本冗余，兼容以下情况：
    1. 同音字抖动（如：花费 -> 花呗）
    2. 边界错位（如：花费了一千 -> 费的一千多）
    3. 避免正常上下文发音相似被误删（如：账号 -> 好像）
    """

    def __init__(self, min_match_len: int = 2, max_skip_len: int = 2, lookback: int = 15) -> None:
        """
        Parameters
        ----------
        min_match_len : int
            触发去重的最小连续匹配字数。推荐 2 或 3。
            比如连续匹配上 "一千" (2个字) 才认为是重叠。
        max_skip_len : int
            当前文本开头允许跳过的最大不匹配字数。
            用于处理 "花费了一千" -> "费的一千多" 这种错位情况。
        lookback : int
            从上一段文本末尾取多少个字参与匹配。提高性能并防止跨句误删。
        """
        self._prev_pinyin: list[str] = []
        self._prev_text: str = ""
        
        self.min_match_len = min_match_len
        self.max_skip_len = max_skip_len
        self.lookback = lookback

    def correct(self, sentence: Sentence) -> Sentence:
        text = sentence.text.strip()

        # 初始化或遇到空文本，直接记录并返回
        if not self._prev_text or not text:
            self._prev_pinyin = lazy_pinyin(text)
            self._prev_text = text
            return sentence

        # 1. 提取拼音（仅取上一段的后半部分和当前段的前半部分）
        prev_py_window = self._prev_pinyin[-self.lookback:]
        curr_py_window = lazy_pinyin(text)
        
        # 限制当前文本参与匹配的长度，避免太长影响性能
        curr_py_match_window = curr_py_window[:self.lookback]

        # 2. 使用 difflib 寻找拼音列表的最长连续匹配块
        sm = difflib.SequenceMatcher(None, prev_py_window, curr_py_match_window)
        match = sm.find_longest_match(0, len(prev_py_window), 0, len(curr_py_match_window))

        # 3. 判断是否满足截断条件
        # match.size 是连续匹配的长度
        # match.b 是匹配块在当前文本拼音列表中的起始索引（即开头跳过的字数）
        if match.size >= self.min_match_len and match.b <= self.max_skip_len:
            
            # 计算要截断的字数：开头跳过的字数 + 连续匹配上的字数
            cut_len = match.b + match.size
            
            # 防御性编程：如果截断长度占当前文本一半以上，可能是异常匹配，放弃截断
            if cut_len < len(text):
                text = text[cut_len:].strip()
                # 同步更新当前文本的拼音列表（截断对应部分）
                curr_py_window = curr_py_window[cut_len:]

        # 4. 更新状态并返回
        self._prev_pinyin = curr_py_window
        self._prev_text = text
        sentence.text = text
        
        return sentence
