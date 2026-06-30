# SpeechNote

> 一款面向学习、会议和创作的本地 AI 语音笔记软件。

SpeechNote 将麦克风语音实时转换为结构化 Markdown 笔记，采用事件驱动 Pipeline 架构，各模块低耦合、可独立替换。

**当前版本：v0.3 Alpha** — 管线已全部打通，PySide6 GUI 可用。

---

# 快速开始

## 一键启动 GUI

双击 `run_gui.bat`，或终端运行：

```bash
python main.py --gui
```

## 命令行模式

```bash
python main.py
# 录音开始 → 自动识别 → 输出到 notes/*.md
# Ctrl+C 退出
```

---

# 系统架构

```
┌──────────────────────────────────────────────────────┐
│                   PySide6 GUI                        │
│  ┌────────────────────────────────────────────────┐  │
│  │  实时字幕（最新一句高亮，自动滚动）             │  │
│  ├────────────────────────────────────────────────┤  │
│  │  历史笔记（所有已输出的 Sentence）              │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │  状态栏：录音中 | VAD | 麦克风 | 00:23        │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                │ 订阅 EventBus
                ▼
┌──────────────────────────────────────────────────────┐
│                   Python 后端                         │
│                                                      │
│  Microphone                                          │
│      │                                               │
│      ▼                                               │
│  RingBuffer          ← 100ms 一帧                    │
│      │                                               │
│      ▼                                               │
│  ASRWorker           ← 缓存/VAD/窗口调度             │
│      │                                               │
│      ▼                                               │
│  Paraformer-large    ← FunASR CPU 推理               │
│      │                                               │
│      ▼                                               │
│  CorrectorPipeline   ← 责任链处理                    │
│      │                                               │
│      ▼                                               │
│  EventBus ────────── → Plugins + GUI                 │
└──────────────────────────────────────────────────────┘
```

---

# 当前功能（v0.3 Alpha）

## v0.1 — 基础设施
- [x] Config 配置中心（dataclass, slots=True, frozen=True）
- [x] Logger 日志系统
- [x] EventBus 事件总线（发布/订阅）
- [x] Sentence 统一数据模型（raw_text / text / metadata）
- [x] Application 生命周期（init → initialize → start → wait → stop）
- [x] assert 消除 Optional（生命周期初始化完成后 IDE 自动收窄类型）
- [x] RingBuffer（线程安全，基于 queue.Queue）

## v0.2 — 录音与 ASR 管线
- [x] MicrophoneRecorder（sounddevice，100ms / 1600 samples 一帧）
- [x] Paraformer-large 中文语音识别（FunASR，CPU 推理）
- [x] _clean_text() — 去除 SenseVoice `<|tag|>` 标签
- [x] Worker 音频缓存（累计 → 拼接 → 识别）
- [x] 重叠窗口（Overlap Window，1s 重叠防切句）
- [x] DuplicateCorrector（最长后缀-前缀匹配去重，倒序 break）
- [x] CorrectorPipeline（责任链模式，Worker 零耦合）
- [x] TermCorrector（词典纠错器：拼音模糊 + 精确替换，94 条热词/术语）
- [x] 识别异常保护（try-except，线程不退出）

## v0.3 — VAD + 模式系统 + GUI
- [x] 能量检测 VAD（零依赖，RMS 阈值 0.005）
- [x] 双模式：mode = "vad" | "window"
  - "vad"：静音 1s 即 flush，适合对话
  - "window"：固定 8s 窗口 + 1s overlap，适合独白
- [x] PySide6 GUI 主窗口（实时字幕 + 历史记录 + 状态栏）
- [x] EventBus → Qt 信号桥接（线程安全）
- [x] 快捷键：Ctrl+R / Ctrl+Shift+R / Ctrl+K / Ctrl+,
- [x] 设置对话框（Config 自动生成表单）
- [x] TermCorrector 四项优化：长度缓存 / 只扫中文 / 连续纠错 / 贪心长词优先
- [x] run_gui.bat — Windows 一键启动

---

# 项目结构

```
SpeechNote/
├── main.py                  # 入口（--gui 切换 GUI/CLI 模式）
├── app.py                   # Application 生命周期管理
├── config.py                # 全局配置
├── run_gui.bat              # Windows 一键启动
├── AGENTS.md                # 项目知识库
│
├── core/
│   ├── event.py             # EventBus 发布/订阅
│   ├── events.py            # 事件类型枚举
│   ├── sentence.py          # Sentence 数据模型
│   └── logger.py            # 日志配置
│
├── audio/
│   ├── base.py              # BaseRecorder 抽象接口
│   ├── recorder.py          # MicrophoneRecorder
│   └── ringbuffer.py        # RingBuffer
│
├── asr/
│   ├── base.py              # BaseRecognizer 抽象接口
│   ├── recognizer.py        # SenseVoiceRecognizer（可切换模型）
│   └── worker.py            # ASRWorker（核心调度器）
│
├── corrector/
│   ├── base.py              # BaseCorrector 抽象接口
│   ├── identity.py          # 直通
│   ├── duplicate.py         # 重复去除
│   └── pipeline.py          # CorrectorPipeline
│
├── plugins/
│   ├── base.py              # BasePlugin 抽象接口
│   └── markdown.py          # MarkdownPlugin
│
├── gui/                     # PySide6 桌面界面
│   ├── __init__.py
│   ├── app.py               # QApplication 入口
│   ├── main_window.py       # 主窗口布局 + 快捷键
│   ├── subtitle_widget.py   # 实时字幕（22pt 高亮）
│   ├── history_widget.py    # 历史记录（自动滚动）
│   ├── status_bar.py        # 状态栏
│   ├── sidebar.py           # 侧边栏
│   ├── settings_dialog.py   # 设置对话框
│   └── event_bridge.py      # EventBus → Qt 信号桥接
│
└── notes/                   # 笔记输出目录（自动生成）
```

---

# 设计原则

## 单一职责

- **Recorder** — 只采集声音
- **Recognizer** — 只负责模型推理
- **Worker** — 只负责"什么时候送识别"
- **Pipeline** — 只负责文本处理
- **Plugin** — 只负责输出
- **GUI** — 只负责显示（不处理业务逻辑）

## Pipeline（责任链）

所有文本统一经过 CorrectorPipeline，新增 Corrector 只需在列表加一行。

## Event Driven（事件驱动）

所有输出通过 EventBus，新增 GUI/Web/API 无需修改识别模块。

## Configuration First

所有可调参数集中于 config.py，改参数不需改代码。

---

# 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+R | 开始/暂停录音 |
| Ctrl+Shift+R | 停止录音 |
| Ctrl+K | 清空当前字幕 |
| Ctrl+, | 打开设置 |

---

# 已实现优化

## Audio Cache + Overlap

```
Chunk1 Chunk2 ... ChunkN → np.concatenate() → Recognizer
                                                      ↓
                                              保留最后 1s overlap
```

## DuplicateCorrector

最长后缀-前缀匹配（倒序遍历，首次命中 break）。

## VAD 双模式

- "vad"（默认）— 静音 1s 即 flush
- "window" — 固定 8s 窗口 + 1s 重叠

## Error Recovery

Worker 内部 try-except，识别异常不退出线程。

---

# 开发路线图

## 近期待做

- [ ] 大模型的分句有严重问题，容易导致逻辑不连贯，加入graph与大模型协作效果应该更好
- [ ] 不能识别电脑声音并与麦克风自由转换
- [ ] 打包出现大量问题
- [ ] VAD 阈值自适应 / GPU 推理支持

## 中期目标

- [ ] Sentence Accumulator
- [ ] 翻译 / 摘要 / 待办 Plugin

## 长期愿景

流式解码修正 / 热词语言模型 / 个人化学习

---

# 已知问题

- CUDA kernel 不兼容，当前 CPU 推理
- Paraformer-large 非流式，有固定感受窗口
- 能量 VAD 在强噪音环境不够准确
- 逐条输出逐条解析的策略让大模型

---

# License

MIT
