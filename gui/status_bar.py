'''状态栏组合，包含音频来源切换。'''


from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox
from PySide6.QtCore import Signal


class StatusBar(QWidget):
    source_changed = Signal(str, str)  # (source_type, file_path)

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        self.record_label = QLabel("⏸ 就绪")
        self.mode_label = QLabel("VAD")
        self.time_label = QLabel("00:00")

        self.source_combo = QComboBox()
        self.source_combo.addItems(["🎤 麦克风", "🔊 系统音频", "📁 文件"])
        self.source_combo.setCurrentIndex(0)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)

        layout.addWidget(self.record_label)
        layout.addWidget(QLabel("|"))
        layout.addWidget(self.mode_label)
        layout.addWidget(QLabel("|"))
        layout.addWidget(QLabel("来源:"))
        layout.addWidget(self.source_combo)
        layout.addWidget(QLabel("|"))
        layout.addWidget(self.time_label)
        layout.addStretch()

    def _on_source_changed(self, index: int):
        """用户切换了音频来源，发射信号交给 MainWindow 处理。"""
        source_type = ["microphone", "system", "file"][index]
        self.source_changed.emit(source_type, "")

    def update_field(self, key, value):
        if key == "recording":
            self.record_label.setText("🔴 录音中" if value == "true" else "⏸ 暂停")
        elif key == "mode":
            self.mode_label.setText(value)
        elif key == "time":
            self.time_label.setText(value)
        elif key == "source":
            idx = {"microphone": 0, "system": 1, "file": 2}.get(value, 0)
            self.source_combo.blockSignals(True)
            self.source_combo.setCurrentIndex(idx)
            self.source_combo.blockSignals(False)
