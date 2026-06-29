"""模糊拼音+词频纠错器。

对于时代热词和领域常用词无法识别的情况，
这个纠错器可以通过词典方式进行纠错。

以后引入大模型进行词典热更新。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from collections import Counter
from pypinyin import lazy_pinyin

from core.sentence import Sentence
from corrector.base import BaseCorrector
from core.logger import get_logger


class TermCorrector(BaseCorrector):
    """基于词典的术语纠错器，支持精确匹配和拼音模糊匹配。"""

    def __init__(
        self,
        dict_path: str | Path = "corrector/correct_dic.json",
        use_pinyin_fuzzy: bool = True,
    ) -> None:
        """
        Parameters
        ----------
        dict_path
            词典 JSON 文件路径。
        use_pinyin_fuzzy
            是否开启拼音模糊匹配。
        """
        self._logger = get_logger()
        self._dict_path = Path(dict_path)
        self._use_pinyin_fuzzy = use_pinyin_fuzzy
        self._term_dict: dict[str, str] = {}
        self._py_to_right: dict[str, str] = {}
        self._term_lengths: set[int] = set()
        self._error_counter: Counter = Counter()
        self._load_dict()

    # ── 工具：只提取中文字符 ──────────────────────────────
    @staticmethod
    def _extract_chinese(text: str) -> tuple[list[str], list[int]]:
        """提取中文字符和它们在原字符串中的索引。"""
        chars: list[str] = []
        indices: list[int] = []
        for idx, ch in enumerate(text):
            if "\u4e00" <= ch <= "\u9fff":
                chars.append(ch)
                indices.append(idx)
        return chars, indices

    # ── 加载词典 ───────────────────────────────────────────
    def _load_dict(self) -> None:
        """加载词典并构建拼音映射和长度缓存。"""
        if not self._dict_path.exists():
            self._logger.warning(
                "术语词典文件不存在: %s，TermCorrector 将不生效。",
                self._dict_path,
            )
            return

        try:
            with open(self._dict_path, "r", encoding="utf-8-sig") as f:
                raw_dict = json.load(f)

            self._term_dict = raw_dict

            # 构建拼音映射 + 缓存长度
            if self._use_pinyin_fuzzy:
                for right_term in set(raw_dict.values()):
                    py = lazy_pinyin(right_term)
                    py_str = "".join(py)
                    self._py_to_right[py_str] = right_term
                    self._term_lengths.add(len(py))

            self._logger.info(
                "加载术语词典成功，共 %d 条精确规则，%d 条模糊规则。",
                len(self._term_dict),
                len(self._py_to_right),
            )

        except json.JSONDecodeError as e:
            self._logger.error("术语词典 JSON 格式错误: %s", e)
        except Exception as e:
            self._logger.error("加载术语词典失败: %s", e)

    # ── 精确匹配 ───────────────────────────────────────────
    def _do_exact_match(self, text: str) -> tuple[str, bool]:
        """精确匹配替换，返回 (新文本, 是否修改)。"""
        modified = False
        for wrong_term, right_term in self._term_dict.items():
            if wrong_term in text:
                count = text.count(wrong_term)
                text = text.replace(wrong_term, right_term)
                self._error_counter[wrong_term] += count
                modified = True
        return text, modified

    # ── 拼音模糊匹配 ───────────────────────────────────────
    def _do_fuzzy_match(self, text: str) -> str:
        """拼音模糊匹配替换（跳过非中文）。"""
        if not self._use_pinyin_fuzzy or not self._py_to_right:
            return text

        changed = True
        while changed:
            changed = False

            chars, indices = self._extract_chinese(text)
            if not chars:
                break

            text_pinyins = lazy_pinyin(chars)

            for length in sorted(self._term_lengths, reverse=True):
                if length > len(text_pinyins):
                    continue
                for i in range(len(text_pinyins) - length + 1):
                    py_window = "".join(text_pinyins[i:i + length])
                    if py_window in self._py_to_right:
                        start = indices[i]
                        end = indices[i + length - 1] + 1
                        wrong_word = text[start:end]
                        right_word = self._py_to_right[py_window]
                        if wrong_word != right_word:
                            text = text[:start] + right_word + text[end:]
                            self._error_counter[wrong_word] += 1
                            changed = True
                            break
                if changed:
                    break

        return text

    # ── 纠错入口 ───────────────────────────────────────────
    def correct(self, sentence: Sentence) -> Sentence:
        """执行词典纠错。"""
        if not self._term_dict and not self._py_to_right:
            return sentence

        text = sentence.text
        original_text = text

        # 1. 精确匹配
        text, _ = self._do_exact_match(text)

        # 2. 拼音模糊匹配
        text = self._do_fuzzy_match(text)

        if text != original_text:
            self._logger.debug(
                "术语纠错触发: '%s' -> '%s'", original_text, text
            )
            sentence.text = text

        return sentence

    def get_error_stats(self) -> dict:
        """获取错误词频统计，方便后续优化词典。"""
        return dict(self._error_counter)
