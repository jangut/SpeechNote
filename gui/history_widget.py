'''
滚动历史记录，只读文本编辑框。
'''


from PySide6.QtWidgets import QTextEdit
from PySide6.QtGui import QFont, QTextCursor


class HistoryWidget(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setPlaceholderText("笔记将显示在这里...")
        font = QFont("Segoe UI", 12)
        self.setFont(font)
        self.setStyleSheet("background-color: #fafafa; border: none;")
        self._sentence_map: dict[str, int] = {}

    def append_sentence(self, sentence):
        """追加新句子到历史列表。"""
        self.append(f"- {sentence.text}")
        self._sentence_map[str(sentence.id)] = self.document().blockCount() - 1
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def update_sentence(self, sentence):
        """
        更新或追加句子。

        若 sentence.id 已存在于历史中则原地替换文本，
        否则追加新行。
        """
        sid = str(sentence.id)
        block_num = self._sentence_map.get(sid)

        if block_num is not None:
            cursor = QTextCursor(self.document().findBlockByNumber(block_num))
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cursor.insertText(f"- {sentence.text}")
        else:
            self.append(f"- {sentence.text}")
            self._sentence_map[sid] = self.document().blockCount() - 1
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def clear(self):
        """清空所有历史和映射。"""
        self.clear()
        self._sentence_map.clear()
