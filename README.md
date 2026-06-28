# SpeechNote

> 一款面向学习、会议和创作的本地 AI 语音笔记软件。

SpeechNote 将麦克风语音实时转换为结构化 Markdown 笔记，并提供可扩展的文本处理流水线，为后续 AI 润色、知识整理、全文检索等功能提供统一架构。

---

# 项目目标

SpeechNote 的目标并不是做一个简单的"语音转文字"程序，而是搭建一套完整的本地 AI 笔记工作流。

整体流程如下：

```
Microphone
      │
      ▼
Recorder
      │
      ▼
RingBuffer
      │
      ▼
ASRWorker
      │
      ▼
SenseVoiceRecognizer
      │
      ▼
Sentence
      │
      ▼
CorrectorPipeline
      │
      ├── DuplicateCorrector
      ├── DictionaryCorrector（Future）
      ├── LLMCorrector（Future）
      └── ...
      │
      ▼
EventBus
      │
      ▼
Plugins
      ├── Markdown
      ├── SQLite（Future）
      ├── Qt GUI（Future）
      └── ...
```

整个系统采用事件驱动架构，各模块之间低耦合，可以独立替换和扩展。

---

# 当前功能（v0.3 Alpha）

## v0.1 — 基础设施
- [x] 项目架构：Config、Logger、EventBus、Sentence 统一数据模型
- [x] Application 生命周期：__init__ → initialize → start → wait → stop
- [x] assert 消除 Optional（生命周期初始化完成后不为空）
- [x] RingBuffer（线程安全，基于 queue.Queue）

## v0.2 — 录音与 ASR 管线
- [x] MicrophoneRecorder（sounddevice，100ms 一帧）
- [x] SenseVoiceRecognizer（FunASR，CPU推理）
- [x] _clean_text() — 去除 SenseVoice `<|tag|>` 标签
- [x] Worker 音频缓存（累计到固定窗口 → 拼接 → 识别）
- [x] 重叠窗口（Overlap Window，1s 重叠防切句）
- [x] DuplicateCorrector（最长后缀-前缀匹配去重）
- [x] CorrectorPipeline（责任链模式）
- [x] 识别异常保护（try-except，发 ERROR 事件，线程不退出）

## v0.3 — VAD + 模式系统
- [x] 能量检测 VAD（零依赖，RMS 阈值 0.005）
- [x] 双模式系统：`mode = "vad"` | `"window"`
  - `"vad"`：VAD 静音即 flush，无重叠，适合对话
  - `"window"`：固定窗口 + overlap，VAD 仅过滤前导静音

---

# 项目结构

```
SpeechNote/

main.py

app.py

config.py

core/
    event_bus.py
    events.py
    logger.py
    sentence.py

audio/
    recorder.py
    ring_buffer.py

asr/
    base.py
    recognizer.py
    worker.py

corrector/
    base.py
    identity.py
    duplicate.py
    pipeline.py

plugin/
    markdown.py
```

所有模块职责单一：

- Recognizer → 识别
- Worker → 调度
- Corrector → 文本处理
- Plugin → 输出

任何模块都可以独立替换。

---

# 设计原则

## 单一职责（Single Responsibility）

每个模块只负责一件事情。

例如：
- Recorder 只采集声音
- Recognizer 只负责识别
- Corrector 只负责文本修正
- Plugin 只负责输出

## Pipeline（流水线）

所有文本统一经过：

```
Sentence → CorrectorPipeline → Sentence
```

以后增加 AI 修正、专业术语、标点恢复、人名识别，无需修改 Worker 和 Recognizer。

## Event Driven（事件驱动）

所有输出均通过 EventBus。新增 GUI、SQLite、HTTP API 无需修改识别模块。

## Configuration First

所有参数均由 Config 控制，避免 Magic Number。

---

# 已实现优化

## Audio Cache

Worker 自动缓存多个 Audio Block 后统一识别，降低推理次数，提高识别准确率。

## DuplicateCorrector

采用最长后缀-前缀匹配（倒序查找，首次命中即 break）。

示例：

```
上一句：大家下午好
下一句：下午好今天开始
    ↓
输出：今天开始
```

## VAD + 双模式

基于 RMS 能量检测的 VAD，零额外依赖。

- `mode = "vad"`：静音0.5秒即 flush，适合对话场景
- `mode = "window"`：固定4秒窗口 + 重叠，适合安静环境

## Error Recovery

Worker 内部统一 try-except，任何识别异常不会导致线程退出。

---

# 开发路线图

## 📋 近期待做

### v0.4 — Corrector 增强

- [ ] **DictionaryCorrector（热词纠正）**
  - `config.py` 新增 `hotwords: list[str]`
  - 编辑距离 ≤ 1 替换
  - 示例：`"SpeechNote"`、`"OpenAI"`、`"深度学习"`

- [ ] **NumberCorrector（数字格式化）**：`"一二三四"` → `"1234"`
- [ ] **PunctuationCorrector（标点恢复）**：句末自动加标点

### v0.5 — 体验优化

- [ ] VAD 阈值自适应（根据环境噪音自动调整）
- [ ] `silence_timeout` 动态调整（语速快时缩短，慢时延长）
- [ ] GPU 推理支持（修复 CUDA kernel 兼容性）
- [ ] 识别结果合并（同一句话的多个片段自动拼接）

## 🚀 中期目标

### v1.0 — AI 增强

- [ ] **LLMCorrector**（接入大模型，上下文感知纠错）
  - `"Chat"` → 知道在聊 AI，不改成 `"Cat"`
  - `"GTP"` → 猜到是 `"GPT"`
- [ ] 对话历史维护
- [ ] 专业术语自动识别
- [ ] **Sentence Accumulator**（累积完整段落后再发送到 Plugin）

### v1.1 — 插件系统

- [ ] 语音转文字实时预览 Plugin
- [ ] 翻译 Plugin（中→英 / 英→中）
- [ ] 摘要 Plugin
- [ ] 待办提取 Plugin

## 🌟 长期愿景（微信输入法级体验）

参考微信输入法语音输入的核心能力：

### 流式解码与回溯修正

```
音频 → 实时解码 → 显示草稿
        ↓
积累更多上下文 → 回溯修正前面
```

每 100ms 出一版结果，后一版覆盖前一版，用户看到的是不断优化的过程。**需要模型层支持**（SenseVoice 目前不支持流式）。

### 热词与语言模型二遍解码

```
第一遍：声学模型 → N 个候选句子
第二遍：语言模型 + 热词 → 重新排序
```

- DictionaryCorrector 的基础版 ✓（热词替换）
- 完整版需要：通讯录/常用语自动导入、用户使用频率统计、解码器级别的重排序

### 个人化学习

越用越准：你的名字、常用地址、公司名。基于 LLM 的个性化纠错，多设备同步热词库。

### 未来 4.x — Qt 桌面应用

- [ ] 实时语音转文字显示
- [ ] 历史记录管理
- [ ] 每个 Corrector 的可视化标注（利用 `sentence.metadata`）
- [ ] 热词管理界面

---

## 🐛 已知问题

- CUDA kernel 不兼容（`torch.AcceleratorError`），当前使用 CPU 推理
- 100ms 单片过短，VAD + 窗口方案缓解但未根除
- FunASR fsmn-vad streaming 模型需要状态管理，暂用能量检测替代

---

# License

MIT
