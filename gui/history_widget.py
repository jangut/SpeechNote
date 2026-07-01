'''
滚动历史记录，连续段落模式。
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

    def append_sentence(self, sentence):
        """追加句子到文本末尾（连续段落，无 bullet）。"""
        text = sentence.text.strip()
        if not text:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        if self.toPlainText():
            cursor.insertText(" ")
        cursor.insertText(text)
        self.setTextCursor(cursor)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def update_sentence(self, sentence):
        """追加句子（连续段落模式）。"""
        self.append_sentence(sentence)

    def clear(self):
        """清空所有历史。"""
        super().clear()
