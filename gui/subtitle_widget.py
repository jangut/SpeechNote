"""
最新句子展示，高亮动画。
"""
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer


class SubtitleWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        layout = QVBoxLayout(self)
        self.label = QLabel("🎯 等待语音...")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        font = self.label.font()
        font.setPointSize(22)
        self.label.setFont(font)
        layout.addWidget(self.label)
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._restore_style)

    def show_sentence(self, sentence):
        self.label.setText(sentence.text)
        self.label.setStyleSheet("background-color: #fff3cd; border-radius: 8px;")
        self._timer.start(1200)

    def _restore_style(self):
        self.label.setStyleSheet("")

    def clear(self):
        self.label.setText("🎯 等待语音...")
        self.label.setStyleSheet("")
