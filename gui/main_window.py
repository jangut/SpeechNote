"""
主窗口，拼合所有控件。
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut

from .subtitle_widget import SubtitleWidget
from .history_widget import HistoryWidget
from .status_bar import StatusBar
from .sidebar import Sidebar
from .settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self, config, event_bridge, backend_controller):
        super().__init__()
        self.config = config
        self.bridge = event_bridge
        self.backend = backend_controller
        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()

    def _setup_ui(self):
        self.setWindowTitle(f"🎤 {self.config.app_name} v{self.config.version}")
        self.resize(960, 680)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 左侧边栏
        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar, 1)

        # 右侧面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self.subtitle = SubtitleWidget()
        self.history_raw = HistoryWidget()
        self.history_raw.setPlaceholderText("🗣 语音识别输出")
        self.history_corrected = HistoryWidget()
        self.history_corrected.setPlaceholderText("🤖 LLM 修正输出")
        self.status_bar = StatusBar()

        # 上下结构：上字幕，下左右双列
        history_splitter = QSplitter(Qt.Horizontal)
        history_splitter.addWidget(self.history_raw)
        history_splitter.addWidget(self.history_corrected)
        history_splitter.setStretchFactor(0, 1)
        history_splitter.setStretchFactor(1, 1)

        outer_splitter = QSplitter(Qt.Vertical)
        outer_splitter.addWidget(self.subtitle)
        outer_splitter.addWidget(history_splitter)
        outer_splitter.setStretchFactor(0, 2)
        outer_splitter.setStretchFactor(1, 3)

        right_layout.addWidget(outer_splitter, 1)
        right_layout.addWidget(self.status_bar)

        main_layout.addWidget(right_panel, 5)

        # 侧边栏信号
        self.sidebar.settings_requested.connect(self._show_settings)
        self.sidebar.help_requested.connect(self._show_help)

    def _connect_signals(self):
        self.bridge.sentence_received.connect(self._on_sentence)
        self.bridge.status_changed.connect(self.status_bar.update_field)

    def _on_sentence(self, sentence):
        self.subtitle.show_sentence(sentence)
        if sentence.llm_corrected:
            self.history_corrected.update_sentence(sentence)
        else:
            self.history_raw.update_sentence(sentence)

    def _show_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            new_conf = dlg.get_config_dict()
            QMessageBox.information(self, "提示", "设置将在重启后生效")

    def _show_help(self):
        QMessageBox.about(self, "帮助",
                          "SpeechNote 帮助\n\n"
                          "Ctrl+R 开始/暂停录音\n"
                          "Ctrl+Shift+R 停止录音\n"
                          "Ctrl+K 清空当前显示\n"
                          "Ctrl+, 打开设置")

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+R"), self, self._toggle_recording)
        QShortcut(QKeySequence("Ctrl+Shift+R"), self, self._stop_recording)
        QShortcut(QKeySequence("Ctrl+K"), self, self._clear_display)
        QShortcut(QKeySequence("Ctrl+,"), self, self._show_settings)

    def _toggle_recording(self):
        if self.backend.is_running:
            self.backend.pause()
            self.status_bar.update_field("recording", "false")
        else:
            self.backend.start()
            self.status_bar.update_field("recording", "true")

    def _stop_recording(self):
        self.backend.stop()
        self.status_bar.update_field("recording", "false")

    def _clear_display(self):
        self.subtitle.clear()
        self.history_raw.clear()
        self.history_corrected.clear()
