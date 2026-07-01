# SpeechNote 项目知识库

## 一句话

SpeechNote 是一个本地 AI 语音笔记软件，将麦克风 / 系统音频 / 文件音频实时转换为结构化 Markdown 笔记，采用事件驱动、Pipeline 流水线架构，支持 LLM 纠错。

---

## 技术栈

```
语言：Python 3.10
ASR：FunASR + SenseVoiceSmall（CPU 推理）
音频：sounddevice + numpy
GUI：PySide6（Qt6 for Python）
纠错：Dict + pypinyin + LLM（Ollama / OpenAI 等）
打包：PyInstaller
```

---

## 架构总览

```
┌──────────────────────────────────────────────────────┐
│                   PySide6 GUI                        │
│  ┌────────────────────────────────────────────────┐  │
│  │  实时字幕（最新一句高亮，自动滚动）              │  │
│  ├────────────────────────────────────────────────┤  │
│  │  历史笔记（所有已输出的 Sentence）               │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │  状态栏：🔴 录音中 | VAD | 来源切换 | 00:23  │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                │ 订阅 EventBus
                ▼
┌──────────────────────────────────────────────────────┐
│                   Python 后端                         │
│                                                      │
│  Mic / System / File   ← 运行时切换                  │
│      │                                               │
│      ▼                                               │
│  RingBuffer          ← 100ms 一帧                    │
│      │                                               │
│      ▼                                               │
│  ASRWorker           ← 缓存/VAD/窗口调度             │
│      │                                               │
│      ▼                                               │
│  SenseVoice          ← FunASR CPU 推理               │
│      │                                               │
│      ▼                                               │
│  CorrectorPipeline   ← 去重 → 词典 → LLM            │
│      │                                               │
│      ▼                                               │
│  EventBus ────────── → Plugins + GUI                 │
└──────────────────────────────────────────────────────┘
```

---

## 核心设计决策

### 1. PySide6 直连 EventBus（不分开跑）

Python 后端和 GUI 在同一个进程内，EventBus 的信号直接连 Qt 信号槽，零 IPC，零延迟。

### 2. Config 配置驱动

所有参数集中在 config.py，Qt 设置界面可遍历字段自动生成表单。

### 3. assert 消除 Optional

生命周期初始化完成后，成员理论上绝不 None，此后 IDE 类型自动收窄。

### 4. CorrectorPipeline（责任链）

```python
self._pipeline = CorrectorPipeline([
    DuplicateCorrector(),   # 拼音去重
    TermCorrector(),        # 词典纠错（精确 + 拼音模糊）
    LLMCorrector(),         # 大模型上下文纠错（异步非阻塞）
])
```

### 5. 双模式识别 + 三音频源

| 模式 | 行为 |
| --- | --- |
| `mode = "vad"`（默认） | VAD 检测到静音即 flush |
| `mode = "window"` | 固定窗口 + overlap |

| 来源 | 实现 | 用途 |
| --- | --- | --- |
| microphone | `MicrophoneRecorder`（sounddevice） | 麦克风输入 |
| system | `SystemAudioRecorder`（VB-CABLE） | 系统音频捕获 |
| file | `FileRecorder`（soundfile） | 文件转录 |

---

## 目录结构

```
SpeechNote/
├── main.py                  # 入口
├── app.py                   # Application 生命周期
├── config.py                # 全局配置
├── build.bat                # PyInstaller 打包脚本
├── AGENTS.md                # 本文件
├── README.md                # 开发路线图
│
├── core/
│   ├── event.py             # EventBus
│   ├── events.py            # 事件类型枚举
│   ├── sentence.py          # Sentence 数据模型
│   ├── exception.py         # 异常定义
│   └── logger.py            # 日志
│
├── audio/
│   ├── base.py              # BaseRecorder
│   ├── mic.py               # MicrophoneRecorder
│   ├── system.py            # SystemAudioRecorder（VB-CABLE）
│   ├── file.py              # FileRecorder
│   └── ringbuffer.py        # RingBuffer
│
├── asr/
│   ├── base.py              # BaseRecognizer
│   ├── recognizer.py        # SenseVoiceRecognizer（ONNX + PyTorch）
│   └── worker.py            # ASRWorker（核心调度）
│
├── corrector/
│   ├── base.py              # BaseCorrector
│   ├── identity.py          # TermCorrector（词典纠错）
│   ├── duplicate.py         # DuplicateCorrector（去重）
│   ├── llm_corrector.py     # LLMCorrector（大模型纠错）
│   └── pipeline.py          # CorrectorPipeline
│
├── plugins/
│   ├── base.py              # BasePlugin
│   └── markdown.py          # MarkdownPlugin
│
├── gui/
│   ├── __init__.py
│   ├── app.py               # QApplication 入口
│   ├── main_window.py       # 主窗口
│   ├── subtitle_widget.py   # 实时字幕
│   ├── history_widget.py    # 历史记录
│   ├── status_bar.py        # 状态栏（含来源切换）
│   ├── sidebar.py           # 侧边栏
│   ├── settings_dialog.py   # 设置对话框
│   └── event_bridge.py      # EventBus → Qt 信号桥接
│
├── corrector/
│   └── correct_dic.json     # 术语词典
│
└── notes/                   # 笔记输出目录（自动生成）
```

---

## 关键文件说明

| 文件 | 职责 | 扩展方式 |
| --- | --- | --- |
| `config.py` | 所有配置 | 加字段 |
| `app.py` | 生命周期 + 音频来源工厂 | `_create_recorder()` 加分支 |
| `mic/system/file.py` | 三种音频源 | 实现 `BaseRecorder` |
| `recognizer.py` | 模型推理 | 换模型时替换 |
| `corrector/` | 文本处理流水线 | 加新类，Pipeline 加一行 |
| `gui/` | PySide6 界面 | 独立模块 |

---

## 当前功能状态（v1.2 Beta）

### 基础设施
- [x] Config 配置中心（dataclass, slots, frozen）
- [x] EventBus 发布/订阅
- [x] Application 生命周期
- [x] RingBuffer 线程安全缓存
- [x] PyInstaller 打包（~900 MB / 压缩后 330 MB）

### 音频源（三源切换）
- [x] MicrophoneRecorder — sounddevice 麦克风
- [x] SystemAudioRecorder — VB-CABLE 虚拟声卡（系统音频）
- [x] FileRecorder — 本地音频文件读取
- [x] 状态栏下拉实时切换
- [x] 设置页面配置默认来源

### ASR
- [x] SenseVoiceSmall（ONNX 优先 / PyTorch 降级）
- [x] _clean_text() 去除标签
- [x] VAD 双模式（vad / window）
- [x] 重叠窗口（overlap，防切句）

### 纠错流水线
- [x] DuplicateCorrector（拼音最长子串去重）
- [x] TermCorrector（词典精确 + 拼音模糊，162 条）
- [x] LLMCorrector（异步非阻塞，支持 Ollama / OpenAI / 通义 / GLM / DeepSeek）
- [x] 标点（ONNX textnorm="withitn"）

### GUI
- [x] PySide6 主窗口
- [x] 实时字幕高亮 + 历史记录
- [x] 状态栏（录音/模式/来源/时长）
- [x] 快捷键（Ctrl+R / Ctrl+Shift+R / Ctrl+K / Ctrl+,）
- [x] 设置对话框（Config 自动生成表单）

### 📋 待做

**v1.3 — 体验优化**
- [ ] Sentence Accumulator（段落累积，解决碎片化输出）
- [ ] LLM 性能优化（上下文窗口、缓存、降频）
- [ ] 专用LLM微调工作

**v1.4 — 工程化**
- [ ] GPU 推理支持
- [ ] VAD 阈值自适应
- [ ] 错误处理和日志改进

**v2.0 — AI 增强**
- [ ] 翻译 / 摘要 / 待办 Plugin
- [ ] 笔记文件浏览器
- [ ] 转录历史管理

---

## 注意事项

- 所有模块通过 EventBus 通信，禁止模块间直接调用
- Worker 只负责"什么时候送识别"，不负责"怎么处理"
- Recognizer 只负责模型推理，不负责缓存或调度
- Corrector 只修改 sentence.text，不修改 raw_text
- Plugin 只订阅事件，不主动拉取
- GUI 只显示，不做任何业务逻辑
- CUDA 当前不可用（kernel 不兼容），全部走 CPU
"@ | Out-File AGENTS.md -Encoding default

# Write README.md
@'
# SpeechNote v1.2 Beta

> 一款面向学习、会议和创作的本地 AI 语音笔记软件。

SpeechNote 将麦克风 / 系统音频 / 音频文件实时转换为结构化 Markdown 笔记，采用事件驱动 Pipeline 架构，各模块低耦合、可独立替换。

**当前版本：v1.2 Beta** — 三源切换 + LLM 纠错 + PySide6 GUI

---

## 快速开始

### 一键启动（已打包版）

```bash
dist\SpeechNote\run_dist.bat
```

### 源码运行

```bash
pip install -r requirements.txt
python main.py                 # GUI 模式
python main.py --cli           # 命令行模式
```

---

## 功能一览

### 三源切换
- **🎤 麦克风** — 实时语音识别
- **🔊 系统音频** — 需安装 VB-CABLE 虚拟声卡
- **📁 文件** — 支持 wav/mp3/flac/m4a 转录

来源可在状态栏实时切换，或在设置页面配置默认。

### 纠错流水线
```
DuplicateCorrector → TermCorrector → LLMCorrector(异步)
```

1. 拼音去重（解决窗口重叠冗余）
2. 词典纠错（精确 + 拼音模糊匹配，162 条）
3. 大模型纠错（Ollama / OpenAI 等）

### GUI
- 实时字幕（最新一句高亮）
- 历史记录（自动滚动）
- 状态栏（录音状态 / 模式 / 来源 / 时长）
- 快捷键：Ctrl+R / Ctrl+Shift+R / Ctrl+K / Ctrl+,

---

## 打包

```bash
build.bat
```

输出 `dist\SpeechNote\`，压缩后约 330 MB。

---

## 设计原则

### 单一职责
- **Recorder** — 只采集声音
- **Worker** — 只负责调度
- **Pipeline** — 只负责文本处理
- **GUI** — 只负责显示

### Pipeline（责任链）
所有文本统一经过 CorrectorPipeline，新增 Corrector 只需在列表加一行。

### Event Driven（事件驱动）
所有输出通过 EventBus，新增端口无需修改识别模块。

### Configuration First
所有参数集中于 config.py，改参数不需改代码。

---

## 系统要求

- Windows 10/11 x64
- Python 3.10+（源码运行）
- 首次启动需联网下载 SenseVoice 模型（~500 MB）
- 推荐：本地 Ollama + Qwen3-8B 等大模型用于纠错

---

## License

MIT
