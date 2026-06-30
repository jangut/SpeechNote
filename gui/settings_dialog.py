"""
从 Config dataclass 自动生成表单，但经过精心分组与美化。
"""

from dataclasses import fields
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QCheckBox, QSpinBox, QDoubleSpinBox,
    QComboBox, QLineEdit, QDialogButtonBox, QGroupBox, QVBoxLayout,
    QTabWidget, QWidget, QScrollArea, QLabel
)

# ── 友好的显示名称映射 ──
_LABELS = {
    # 音频
    "sample_rate": "采样率 (Hz)",
    "channels": "声道数",
    "block_size": "音频块大小 (样本数)",
    # ASR
    "model_dir": "模型目录 / ID",
    "device": "推理设备 (cpu / cuda)",
    # 识别与 VAD
    "mode": "识别模式",
    "recognize_window": "识别窗口 (秒)",
    "overlap_window": "重叠窗口 (秒)",
    "vad_threshold": "VAD 能量阈值",
    "silence_timeout": "静音超时 (秒)",
    "enable_vad": "启用 VAD",
    # LLM
    "llm_provider": "LLM 提供商",
    "llm_base_url": "API 端点",
    "llm_api_key": "API 密钥",
    "llm_model": "模型名称",
    "llm_timeout": "请求超时 (秒)",
    "llm_max_retries": "最大重试次数",
    "llm_max_context_sentences": "上下文句子数",
    "llm_idle_timeout": "静音触发纠错 (秒)",
    "llm_short_text_threshold": "短文本阈值 (字数)",
    "llm_prompt_file": "自定义 Prompt 文件路径",
}

# ── 分组定义（组名 -> 字段名列表） ──
_GROUPS = {
    "🎤 音频设置": ["sample_rate", "channels", "block_size"],
    "🧠 语音识别": ["model_dir", "device"],
    "⚙️ 识别模式与 VAD": ["mode", "recognize_window", "overlap_window",
                        "vad_threshold", "silence_timeout", "enable_vad"],
    "🤖 大模型纠错": ["llm_provider", "llm_base_url", "llm_api_key", "llm_model",
                    "llm_timeout", "llm_max_retries", "llm_max_context_sentences",
                    "llm_idle_timeout", "llm_short_text_threshold", "llm_prompt_file"],
}


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ SpeechNote 设置")
        self.setMinimumWidth(650)
        self.config = config
        self.widgets = {}

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        # 滚动区域（防止内容过长）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        main_layout.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(16)

        # 按分组创建 QGroupBox
        for group_name, field_names in _GROUPS.items():
            group_box = QGroupBox(group_name)
            form = QFormLayout(group_box)
            form.setLabelAlignment(Qt.AlignRight)  # 右对齐标签更整洁
            form.setSpacing(8)

            for fname in field_names:
                # 跳过未在 config 中定义的字段（安全起见）
                if not hasattr(config, fname):
                    continue
                value = getattr(config, fname)
                # 获取字段类型（从 dataclass 中获取）
                field_obj = next((f for f in fields(config) if f.name == fname), None)
                if field_obj is None:
                    continue
                ftype = field_obj.type
                w = self._create_widget(ftype, fname, value)

                # 保存引用
                self.widgets[fname] = w

                # 添加行，使用友好标签
                label_text = _LABELS.get(fname, fname.replace('_', ' ').title())
                form.addRow(label_text, w)

            container_layout.addWidget(group_box)

        # 底部按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        # 应用一点样式表（可选美化）
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QFormLayout QLabel {
                font-weight: normal;
            }
        """)

    def _create_widget(self, ftype, name, value):
        """根据字段类型创建对应的控件。"""
        # bool
        if ftype == bool:
            w = QCheckBox()
            w.setChecked(value)
        # int
        elif ftype == int:
            w = QSpinBox()
            w.setRange(0, 999999)
            w.setValue(value)
            if name in ("sample_rate", "channels", "block_size", "llm_max_retries",
                        "llm_max_context_sentences", "llm_short_text_threshold"):
                w.setRange(1, 999999)  # 保证正数
        # float
        elif ftype == float:
            w = QDoubleSpinBox()
            w.setDecimals(4)
            w.setSingleStep(0.001)
            w.setRange(0.0, 999999.0)
            w.setValue(value)
        # 特殊 combo（mode, provider）
        elif name == "mode":
            w = QComboBox()
            w.addItems(["vad", "window"])
            w.setCurrentText(value)
        elif name == "llm_provider":
            w = QComboBox()
            w.addItems(["ollama", "openai", "qwen", "glm", "deepseek"])
            w.setCurrentText(value)
        # 其他（字符串）
        else:
            w = QLineEdit(str(value))
            if name == "llm_api_key":
                w.setEchoMode(QLineEdit.Password)  # 敏感信息隐藏
            if name == "llm_base_url":
                w.setPlaceholderText("例如 http://localhost:11434/v1/chat/completions")
            if name == "model_dir":
                w.setPlaceholderText("ModelScope 模型 ID 或本地路径")
        return w

    def get_config_dict(self):
        """从控件中读取用户修改后的值，返回字典。"""
        d = {}
        for name, w in self.widgets.items():
            if isinstance(w, QCheckBox):
                d[name] = w.isChecked()
            elif isinstance(w, QSpinBox):
                d[name] = w.value()
            elif isinstance(w, QDoubleSpinBox):
                d[name] = w.value()
            elif isinstance(w, QComboBox):
                d[name] = w.currentText()
            else:
                d[name] = w.text()
        return d
