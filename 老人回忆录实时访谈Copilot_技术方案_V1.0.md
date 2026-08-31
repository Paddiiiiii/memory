# 老人回忆录实时访谈 Copilot——完整开发与技术方案 V1.0

## 1. 产品目标

产品定位：

> **面向专业访谈者的桌面端实时采访辅助系统。**

核心目标不是替代访谈者，而是在一次 2–4 小时深度访谈中实时完成：

1. 主录音可靠保存
2. 实时语音转文字
3. 自动识别采访者/受访者
4. 10 分钟滚动内容分析
5. 自动更新问题清单覆盖情况
6. 自动抽取人物、时间、地点、事件
7. 实时生成人生时间轴
8. 自动发现未展开话题
9. 每 30 分钟分析时间空白、人物空白、事件空白
10. 动态给访谈者推荐下一步问题
11. 提供“人生第一次”记忆触发问题
12. 访谈结束前进行完整性检查
13. Apple Watch 独立录音作为第二音源
14. 访谈结束后双音源重新转写、校准
15. 生成最终可靠文字档案及结构化人生数据库

**现场目标：采得全。**

**访谈后目标：校得准。**

**后续编辑目标：理得清、写得好。**

---

## 2. 推荐技术栈

### 2.1 桌面客户端

首发建议：

### macOS First

技术：

- **Tauri 2**
- Vue 3
- TypeScript
- Rust
- SQLite
- FFmpeg sidecar
- Rust `cpal` 音频采集
- WebSocket

选择 macOS First 的主要原因是 Apple Watch 录音可以通过 iCloud 自动出现在同 Apple Account 的 Mac Voice Memos 中，且录音可以拖到 Finder 导出。

后期再发布：

- Windows
- macOS Universal
- Web 管理后台

不建议核心采访端做成浏览器或微信小程序。

---

## 3. 整体系统架构

```text
┌──────────────────────────────────────────────┐
│                Desktop Client                │
│                                              │
│  外置Mic ── Audio Engine ── 本地FLAC         │
│                     │                        │
│                     ├─ PCM 16k ── Realtime ASR
│                     │                        │
│                     ├─ 实时Transcript        │
│                     │                        │
│                     ├─ Question UI           │
│                     ├─ Timeline UI           │
│                     └─ Suggestion UI         │
│                                              │
│  Local SQLite + Local Audio Storage          │
└──────────────────┬───────────────────────────┘
                   │ HTTPS / WS
                   ▼
┌──────────────────────────────────────────────┐
│                Backend API                   │
│              FastAPI / Python                │
│                                              │
│  Auth / Project / Session / AI Gateway       │
│  Prompt Registry / State Manager             │
└──────────┬──────────┬──────────┬─────────────┘
           │          │          │
           ▼          ▼          ▼
      PostgreSQL    Redis     Object Storage
                              COS / OSS / S3
           │
           ▼
┌──────────────────────────────────────────────┐
│               AI Workflow                    │
│                                              │
│  10m Analyzer        GPT-5.6 Luna            │
│  30m Global Analyzer GPT-5.6 Terra           │
│  Final Review        GPT-5.6 Sol             │
│  Post Replay         Luna/Terra/Sol          │
└──────────────────────────────────────────────┘

Apple Watch
     │
     ▼
独立 Voice Memos
     │
采访结束
     ▼
导入桌面程序
     │
双音轨离线重新转录
     │
对齐 / 比对 / 校正
     ▼
Final Transcript
     │
重新 Replay AI Pipeline
     ▼
Final Interview State
```

---

## 4. 音频系统

### 4.1 现场录音方案

建议实际使用：

### Track A：主音轨

外置无线麦克风 → USB 接收器 → Mac

优先：

**2.4GHz 无线麦克风 + USB-C 接收器**

而不是普通 Bluetooth HFP 麦克风。

软件仍支持任何系统识别到的 Bluetooth Audio Input，但正式访谈优先 USB Audio Device。

### Track B：可选本机安全音轨

建议同时打开：

Mac 内置麦克风。

形成：

```text
Track A = 外置麦克风
Track B = Mac 内置麦克风
Track C = Apple Watch
```

即：

**三重音频保险。**

---

## 5. Apple Watch 录音方案

Apple Watch 不接入实时工作流。

定义为：

> **独立黑匣子录音源。**

流程：

```text
Apple Watch Voice Memos
↓
iCloud
↓
Mac Voice Memos
↓
拖出 / 导入软件
↓
Watch Audio Track
```

第一版不要试图直接访问 Voice Memos 私有数据库。

只支持：

**拖放文件 / 文件选择器导入。**

---

## 6. 双录音同步音

开始正式访谈之前：

1. 先启动 Apple Watch 录音
2. 点击电脑软件“开始采访”
3. 软件发出约 200ms 的同步音
4. 正式采访
5. 结束时电脑再次发同步音
6. 停止 Apple Watch

于是：

```text
PC:
SYNC_START ---------------------- SYNC_END

Watch:
      SYNC_START ---------------------- SYNC_END
```

两个同步点可以精确计算：

- 起始 Offset
- Clock Drift
- 两台设备时间比例偏移

得到：

```text
WatchTime = a × PcTime + b
```

再辅以每 10 分钟一次音频相关性校正。

---

## 7. 本地录音格式

主档案：

```text
48 kHz
24 bit
Mono
FLAC
```

实时 ASR：

```text
16 kHz
16 bit
Mono
PCM
```

实时进行 Resample：

```text
48k source
│
├── FLAC → 本地保存
│
└── 16k PCM → ASR
```

---

## 8. 音频分块

不能保存成单个 4 小时大文件。

推荐：

**60 秒一个 Chunk。**

```text
audio/
├── primary_000001.flac
├── primary_000002.flac
├── primary_000003.flac
...
```

Metadata：

```json
{
  "chunk_id": "01K...",
  "track_id": "primary",
  "start_ms": 360000,
  "end_ms": 420000,
  "sample_rate": 48000,
  "channels": 1,
  "checksum": "sha256...",
  "sync_status": "local"
}
```

---

## 9. 本地优先原则

整个采访过程中：

## Source of Truth

不是云端。

而是：

> **本地音频 + 本地 SQLite。**

网络断线：

```text
录音      ✅继续
本地存储  ✅继续
文字稿    可延迟
AI分析    可延迟
```

网络恢复：

```text
Audio/Transcript Outbox
↓
重新发送
↓
补转录
↓
补跑 Analyzer
↓
State Catch-up
```

---

## 10. 实时 ASR

主方案：

### 腾讯云 `16k_zh_en_speaker_2.0`

Realtime ASR V2 WebSocket。

能力：

- 中文普通话
- 英语
- 粤语
- 四川话
- 河南话
- 上海话
- 湖北/安徽等
- 多种方言
- 实时说话人分离
- 针对远场、噪音、回声等低质量音频增强

### 成本

实时语音识别大模型 2.0：

**约 ¥1 / 小时。**

3 小时：

**约 ¥3。**

---

## 11. ASR 数据结构

所有识别结果转成统一内部格式：

```json
{
  "segment_id": "seg_001239",
  "session_id": "xxx",
  "speaker_id": "speaker_01",
  "start_ms": 734200,
  "end_ms": 742900,
  "raw_text": "我那时候应该是六九年去武汉",
  "status": "final",
  "source": "tencent_live",
  "confidence": 0.91
}
```

Partial：

```text
我那时候应该...
```

只用于 UI。

Final：

```text
我那时候应该是六九年去武汉。
```

才进入 AI Analyzer。

---

## 12. Speaker Mapping

ASR 输出：

```text
speaker_0
speaker_1
speaker_2
```

软件允许人工标记：

```text
speaker_0 → 采访者
speaker_1 → 老人
speaker_2 → 老人的女儿
```

支持 Alias。

不要依赖 AI 自动判断身份。

---

## 13. 实时文字稿

UI 实时显示：

```text
10:42:18  老人
我那时候应该是六九年去武汉。

10:42:25  采访者
当时为什么决定去武汉？

10:42:30  老人
家里面条件不好……
```

必须支持：

- 点击文字播放对应音频
- 快速搜索
- 标记重点
- 手工备注
- 添加书签
- 人工改错
- 当前说话人修正

---

## 14. AI 工作流总体设计

不要运行一个长达 3 小时的 AI Session。

采用：

```text
Realtime Transcript
        │
        ├─ 10 min → Window Analyzer
        │
        ├─ 20 min → Window Analyzer
        │
        ├─ 30 min → Window + Global Analyzer
        │
        ├─ 40 min → Window Analyzer
        │
        ...
        │
        └─ End → Final Coverage Analyzer
```

---

## 15. 10 分钟窗口

实际使用：

**12 分钟文本窗口 + 2 分钟 overlap。**

```text
Analyzer #1  00–10
Analyzer #2  08–20
Analyzer #3  18–30
Analyzer #4  28–40
```

输入：

```text
Recent Transcript
+
Current Interview State
+
Question State
+
Known Entity Index
```

输出：

**State Delta**

---

## 16. 10-Minute Analyzer 模型

推荐：

### GPT-5.6 Luna

任务：

- 人物提取
- 地点提取
- 时间提取
- 事件提取
- 问题覆盖更新
- “第一次”识别
- Open Loop 识别
- 事实候选
- 事件完整度
- Alias 候选

Reasoning：

**low**

必要时提升到 medium。

---

## 17. 每 30 分钟 Global Analyzer

模型：

### GPT-5.6 Terra

输入：

```text
Current Interview State
+
最近30分钟 State Delta
+
Question Coverage
+
Open Loops
```

任务：

- Timeline Gap
- Person Gap
- Event Gap
- Relationship Gap
- Contradiction
- Narrative Gap
- Topic Imbalance
- Suggested Follow-ups

Reasoning：

**medium。**

---

## 18. 结束前 Final Coverage Review

模型：

### GPT-5.6 Sol

Reasoning：

**high。**

输入：

```text
Interview State
+
Timeline
+
People
+
Events
+
Question Coverage
+
Open Loops
+
Conflicts
+
Gap List
+
Important Evidence
```

任务：

生成：

```text
结束前最值得补问的 3–8 个问题
```

而不是几十个。

---

## 19. 不展示 AI 思维过程

后台不要保存或展示 Chain-of-Thought。

只返回：

- Finding
- Evidence
- Confidence
- Suggestion
- Missing Information

例如：

```json
{
  "type": "PERSON_GAP",
  "person_id": "p_023",
  "finding": "母亲可能是重要人物，但信息不足。",
  "evidence": [
    "seg_123",
    "seg_157",
    "seg_342"
  ],
  "confidence": 0.91,
  "suggestion": "可以请老人讲一件最能代表母亲性格的事情。"
}
```

---

## 20. State 架构

核心：

# Interview State

不能是一大段 AI Summary。

必须结构化。

```text
InterviewState
│
├── Timeline
├── People
├── Places
├── Events
├── Relationships
├── Questions
├── FirstExperiences
├── OpenLoops
├── Gaps
├── Conflicts
├── Themes
└── Coverage
```

---

## 21. State 使用 Event Sourcing

不直接覆盖旧 State。

保存：

```text
State v001
Delta 001

State v002
Delta 002

State v003
Delta 003
```

每次：

```text
Old State
+
AI Delta
↓
Validation
↓
Merge Engine
↓
New State
```

因此可以随时：

- Replay
- Debug
- Rollback
- Prompt A/B Test

---

## 22. AI 绝不直接更新数据库

结构：

```text
LLM
↓
Structured Output
↓
JSON Schema Validation
↓
Entity Resolution
↓
Conflict Check
↓
Merge Engine
↓
DB
```

错误输出：

直接丢弃 / Retry。

---

## 23. 核心 Event Schema

```json
{
  "id": "evt_xxx",
  "title": "第一次去武汉",
  "category": "migration",
  "importance": 0.86,

  "time": {
    "raw": "六九年",
    "start": "1969-01-01",
    "end": "1969-12-31",
    "precision": "year",
    "certainty": "probable"
  },

  "people_ids": [
    "person_self",
    "person_wang"
  ],

  "place_ids": [
    "place_wuhan"
  ],

  "summary": "受访者离开家乡前往武汉工作。",

  "completeness": {
    "cause": true,
    "process": true,
    "outcome": true,
    "emotion": false,
    "people": true,
    "place": true
  },

  "missing": [
    "离开时父母的反应",
    "第一次到武汉后的住宿"
  ],

  "evidence": [
    "seg_001",
    "seg_018"
  ]
}
```

---

## 24. 人物 Schema

```json
{
  "id": "person_xxx",
  "name": "王建国",
  "aliases": [
    "老王",
    "王师傅"
  ],
  "relationship": "工作师傅",
  "importance": 0.92,
  "first_mentioned_at": 1943200,
  "mention_count": 12,
  "event_ids": [],
  "evidence": []
}
```

---

## 25. 时间表达必须支持模糊性

禁止把：

> “六九年前后”

直接转换为精确日期。

应记录：

```json
{
  "raw": "六九年前后",
  "start": "1968-01-01",
  "end": "1970-12-31",
  "precision": "approx_year",
  "certainty": "approximate"
}
```

---

## 26. Question Schema

```json
{
  "id": "q_001",
  "topic": "第一次工作",
  "text": "还记得第一次领工资吗？",

  "importance": 0.8,

  "coverage": 0.65,

  "status": "partial",

  "covered_slots": [
    "工资金额",
    "工作地点"
  ],

  "missing_slots": [
    "怎么花",
    "当时心情"
  ],

  "evidence": [
    "seg_182"
  ],

  "last_asked_at": null
}
```

---

## 27. 问题排序不交给 LLM

LLM只计算属性。

程序计算：

```text
score =

importance × 0.25
+
(1 - coverage) × 0.25
+
current_topic_relevance × 0.20
+
story_gap × 0.15
+
life_significance × 0.10
+
first_experience_bonus × 0.05

-
recent_question_penalty
-
sensitive_topic_penalty
-
repeat_penalty
```

界面只浮：

**Top 3–5。**

---

## 28. Open Loop

Schema：

```json
{
  "id": "loop_xxx",
  "quote": "那一年其实差点出了一件大事。",
  "status": "OPEN",
  "importance": 0.91,
  "source_segment_id": "seg_820",
  "created_at": 4834000
}
```

UI模块名称：

## 没说完的故事

---

## 29. 人生第一次系统

建立标准 taxonomy：

```text
EDUCATION_FIRST
WORK_FIRST
MONEY_FIRST
TRAVEL_FIRST
LOVE_FIRST
MARRIAGE_FIRST
PARENT_FIRST
HOME_FIRST
LOSS_FIRST
SUCCESS_FIRST
FAILURE_FIRST
TECH_FIRST
RETIREMENT_FIRST
GRANDPARENT_FIRST
...
```

Event：

```json
{
  "is_first_experience": true,
  "first_type": "FIRST_SALARY"
}
```

---

## 30. “第一次”救场算法

当满足：

```text
老人连续回答较短
OR
当前主题覆盖 > 80%
OR
用户点击“换个方向”
```

系统根据：

```text
年龄段
+
时间线
+
未覆盖 First
+
当前人物
+
当前事件
```

生成最多三个问题。

---

## 31. 时间线 UI

数据全部来源于 Event。

不单独维护第二套事实。

```text
1948
● 出生

1955
● 第一次上学

1962
● 离校

1962 ───────── 1969
       ⚠ TIME GAP

1969
● 去武汉
● 第一份工作

1971?
◐ 认识妻子

1972 / 1973
⚠ CONFLICT
```

---

## 32. 后台数据库

### PostgreSQL

核心表：

```text
users
projects
subjects

interview_sessions

audio_tracks
audio_chunks
sync_points

transcript_segments
transcript_versions

people
person_aliases
places
relationships

events
event_people
event_places
event_evidence

questions
question_evidence

first_experiences

open_loops
gaps
conflicts

analysis_runs
state_deltas
state_snapshots

media_assets
interviewer_notes

prompt_versions
model_usage
```

ID：

**UUIDv7。**

---

## 33. 本地 SQLite

客户端保存：

```text
session
audio_chunk
transcript_segment
outbox
local_note
sync_state
```

使用：

**SQLCipher**

或 SQLite + AES 加密文件层。

密钥存：

macOS Keychain。

---

## 34. Backend

推荐：

### FastAPI

运行：

```text
REST API
WebSocket events
AI Gateway
Prompt Registry
State Merger
Authentication
Usage Metering
```

---

## 35. 异步任务

MVP：

```text
Redis
+
Celery
```

任务：

```text
analyze_10m
analyze_30m
final_review
post_transcribe
audio_align
transcript_merge
replay_state
```

产品规模上来以后切：

### Temporal

用于 Durable Workflow。

---

## 36. Object Storage

使用：

- 腾讯 COS
- 阿里 OSS
- S3

目录：

```text
/{project_id}/
  /sessions/
    /session_id/
      /audio/
      /watch/
      /photos/
      /documents/
```

服务端开启：

- Server Side Encryption
- Lifecycle
- Versioning

---

## 37. Prompt 管理

Prompt绝对不能写死在代码里。

数据库：

```text
prompt_versions
```

字段：

```text
prompt_name
version
model
reasoning_effort
schema_version
prompt_text
active
created_at
```

例如：

```text
WINDOW_ANALYZER_v14
GLOBAL_ANALYZER_v8
FINAL_COVERAGE_v5
TRANSCRIPT_CLEANER_v7
```

---

## 38. 每次 AI 调用完整记录

`analysis_runs`

记录：

```text
model
prompt_version
state_version_in
state_version_out

input_segment_ids

input_tokens
output_tokens

latency
cost

raw_output
validated_output

success
error
```

用于：

- Debug
- 成本分析
- 模型升级
- Prompt A/B测试

---

## 39. Evidence First

整个系统必须执行：

> **没有 Evidence，不进入事实数据库。**

任何：

- 人
- 时间
- 地点
- 事件
- 情绪
- 关系

都必须保存：

```text
source_segment_ids[]
```

UI点击事实：

直接跳：

```text
原始文字
+
原始录音时间点
```

---

## 40. 采访者笔记

单独存。

不能与老人原话混合。

类型：

```text
SOURCE_INTERVIEW
SOURCE_INTERVIEWER_OBSERVATION
SOURCE_FAMILY
SOURCE_PHOTO
SOURCE_DOCUMENT
SOURCE_AI_INFERENCE
```

例如：

> “老人讲到母亲时沉默约20秒。”

来源必须标：

**采访者观察。**

---

## 41. Apple Watch 访谈后处理

正式流程：

```text
PC Primary Audio
+
Apple Watch Audio
↓
FFmpeg decode
↓
16k mono PCM
↓
SYNC detection
↓
Clock Drift Correction
↓
Audio Alignment
```

---

## 42. 对齐算法

一级：

### Sync Tone Matching

确定：

```text
start_offset
end_offset
clock_ratio
```

二级：

每10分钟提取音频 envelope：

```text
RMS energy
spectral fingerprint
```

Cross Correlation：

得到 residual offset。

三级：

Piecewise Linear Mapping。

最终：

```text
Watch timestamp → Canonical PC timestamp
```

误差目标：

**<200ms。**

---

## 43. PC 音频最终转录

使用腾讯：

### Recording File Recognition 2.0

目标：

- 长录音识别
- 多方言
- 说话人分离

参考成本：

**约 ¥0.8 / 小时。**

3小时：

**约 ¥2.4。**

---

## 44. Apple Watch 最终转录

为了避免同模型“共同犯错”，建议换供应商：

### OpenAI GPT-Transcribe

参考价格：

**$0.0045 / 分钟。**

180分钟：

**$0.81。**

用途：

- 第二套独立转录
- 人名/地点/年份交叉验证
- Code-switching
- Keyword hints

---

## 45. 双转录合并

得到：

```text
Transcript Tencent
Transcript OpenAI
```

先按 Canonical Timestamp 切：

**30–60 秒 block。**

再做：

### Token Alignment

采用：

- Levenshtein
- Needleman–Wunsch
- Chinese tokenization

生成：

```text
MATCH
INSERT
DELETE
SUBSTITUTE
```

---

## 46. Canonical Transcript 规则

腾讯：

> 我69年去了武汉。

OpenAI：

> 我69年去了武汉。

结果：

```text
CONFIRMED
```

冲突：

腾讯：

> 我69年去了武昌。

OpenAI：

> 我69年去了武汉。

进入：

```text
DISPUTED
```

---

## 47. 第三意见机制

只有冲突片段重新调用模型。

提取：

```text
冲突前15秒
+
冲突
+
冲突后15秒
```

重新提交。

可以加入 Keyword Hints：

```text
武汉
武昌
王师傅
...
```

仍无法确认：

```text
REQUIRES_HUMAN_REVIEW
```

不允许 LLM 猜。

---

## 48. 正式 Transcript 分三层

### 1. Raw Transcript

忠实。

### 2. Canonical Transcript

双音源校准后的正式原话。

### 3. Clean Transcript

口语整理版。

例如：

原文：

> 我那个，嗯，那时候其实我妈，就是她不吃，给我们吃嘛。

Clean：

> 那时候我妈有时自己不吃，把东西留给我们。

要求：

- 不添加事实
- 不添加情绪
- 不修改日期
- 不创造对白

---

## 49. Transcript Cleaner

模型：

### GPT-5.6 Terra

Reasoning：

low。

输出必须逐 Segment：

```json
{
  "segment_id": "seg_182",
  "raw": "...",
  "clean": "...",
  "changes": [
    "remove_filler",
    "punctuation"
  ]
}
```

保持可溯源。

---

## 50. Final Replay

访谈结束后，不直接沿用 Live State。

流程：

```text
Canonical Transcript
↓
重新按10分钟切片
↓
Luna extraction
↓
Terra global analysis
↓
Sol final consolidation
↓
Final Interview State
```

得到：

### Live Interview State

用途：

> 现场辅助。

### Final Interview State

用途：

> 回忆录编辑。

两者严格分开。

---

## 51. API设计

### Session

```text
POST /v1/projects
POST /v1/sessions
POST /v1/sessions/{id}/start
POST /v1/sessions/{id}/finish
```

### Transcript

```text
POST /v1/transcript/segments
GET  /v1/sessions/{id}/transcript
PATCH /v1/transcript/{segment_id}
```

### Analysis

```text
POST /v1/sessions/{id}/analysis/window
POST /v1/sessions/{id}/analysis/global
POST /v1/sessions/{id}/analysis/final
```

### State

```text
GET /v1/sessions/{id}/state
GET /v1/sessions/{id}/timeline
GET /v1/sessions/{id}/people
GET /v1/sessions/{id}/events
```

### Post Processing

```text
POST /v1/sessions/{id}/watch-audio
POST /v1/sessions/{id}/align
POST /v1/sessions/{id}/retranscribe
POST /v1/sessions/{id}/rebuild
```

---

## 52. WebSocket Event

```text
transcript.partial
transcript.final

speaker.detected

analysis.started
analysis.completed

entity.person.added
entity.person.updated

event.added
event.updated

timeline.updated

question.coverage_updated

open_loop.added
gap.detected
conflict.detected

suggestion.updated

network.status
recording.health
```

---

## 53. 前台核心界面

### Interview Mode

```text
┌─────────────────────────────────────┐
│ ● REC 01:42:18      MIC ███████     │
├────────────────┬────────────────────┤
│                │ 当前建议            │
│ 实时文字稿      │ 1. 王师傅……         │
│                │ 2. 第一次工资……     │
│                │ 3. 母亲……           │
├────────────────┼────────────────────┤
│ 动态问题清单    │ 人生时间线          │
│                │                    │
└────────────────┴────────────────────┘
```

采访者只需要关注：

### Top Suggestions

不要展示过量分析。

---

## 54. 核心按钮

```text
开始采访

添加标记

没说完的故事

人生第一次

换个方向

查看时间线

查看人物

准备收尾
```

---

## 55. 准备收尾

点击：

### 准备收尾

GPT-5.6 Sol分析：

```text
时间缺口
人物缺口
关键事件缺口
未展开话题
事实冲突
人生阶段
问题覆盖
```

返回：

```text
结束前最值得问的问题

1.
2.
3.
4.
5.
```

---

## 56. 音频健康监控

客户端每秒统计：

```text
RMS
peak
clipping
silence
buffer underrun
device disconnected
sample rate
```

出现：

```text
外置麦克风断开
```

自动：

1. UI报警
2. 切换内置麦克风
3. 插入 Device Event
4. 保持录音不中断

---

## 57. 网络故障

使用 Local Outbox Pattern：

```text
event
↓
SQLite Outbox
↓
Network Available?
├ YES → Backend
└ NO  → Wait
```

恢复以后按照 sequence id 重放。

必须保证 idempotency。

---

## 58. 数据安全

### Local

- SQLCipher / AES
- Keychain储存密钥

### Transport

- TLS 1.3

### Server

- PostgreSQL encryption
- Object Storage SSE/KMS
- 独立Project ACL

### Audit

记录：

```text
谁访问
谁下载
谁修改
谁删除
```

---

## 59. 隐私机制

建立：

```text
ConsentRecord
```

记录：

- 受访者
- 同意录音
- 同意AI处理
- 同意存储
- 是否允许家庭成员访问
- 是否允许出版

支持：

### 一键彻底删除

包括：

- Audio
- Transcript
- AI State
- Media
- Backup

如果未来面向中国大陆正式商业化，还应把 **LLM Provider、ASR Provider、对象存储区域**做成可替换配置，以适应不同数据本地化/合规要求。

---

## 60. Provider 抽象层

不要把业务代码绑死腾讯/OpenAI。

```text
ASRProvider

TencentRealtimeASR
TencentFileASR
OpenAITranscribe
```

```text
LLMProvider

OpenAIProvider
DomesticProvider
```

以后可以切：

- OpenAI
- 通义
- 混元
- 豆包
- 私有模型

而无需修改业务逻辑。

---

## 61. 推荐模型最终配置

| 工作 | 模型 |
|---|---|
| 现场实时转录 | Tencent 16k_zh_en_speaker_2.0 |
| 10分钟事件/人物提取 | GPT-5.6 Luna |
| 动态问题覆盖 | GPT-5.6 Luna |
| Open Loop发现 | GPT-5.6 Luna |
| 30分钟全局分析 | GPT-5.6 Terra |
| Gap/Conflict分析 | GPT-5.6 Terra |
| 结束前完整性检查 | GPT-5.6 Sol |
| PC最终ASR | Tencent File ASR 2.0 |
| Watch最终ASR | GPT-Transcribe |
| 文字清理 | GPT-5.6 Terra |
| 最终State重建 | Luna → Terra → Sol |
| 后期章节规划 | GPT-5.6 Sol |
| 后期回忆录写作 | GPT-5.6 Sol |

---

## 62. 三小时访谈变量成本

按一场：

**3小时采访。**

### 实时ASR

Tencent：

```text
3h × ¥1
= ¥3
```

### PC最终离线ASR

```text
3h × ¥0.8
= ¥2.4
```

### Apple Watch GPT-Transcribe

```text
180min × $0.0045
= $0.81
```

---

## 63. LLM成本估算

一场3小时：

### 18次 Luna Window

假设合计：

```text
90K input
18K output
```

约：

**$0.04**

### 6次 Terra Global

假设：

```text
70K input
12K output
```

约：

**$0.28**

### 一次 Sol Final

假设：

```text
30K input
5K output
```

约：

**$0.22**

### Post Replay + Transcript Cleaning + Final State

预算：

**$0.4–0.8**

---

## 64. 单次3小时完整AI变量成本

按预算汇率约 1 USD ≈ ¥7.2 计算：

| 项目 | 成本 |
|---|---:|
| 实时腾讯ASR | ¥3 |
| PC离线ASR | ¥2.4 |
| Watch GPT-Transcribe | ≈¥5.8 |
| 实时Luna分析 | <¥0.5 |
| Terra分析 | ≈¥2 |
| Sol检查 | ≈¥1.5 |
| Post Replay | ≈¥3–6 |
| 少量冲突重识别 | <¥1 |
| **总变量成本** | **约¥18–22** |

工程预算建议：

> **按 ¥25–30 / 每场3小时访谈预留AI/API成本。**

---

## 65. 规模成本

100 场 × 3小时：

AI/API变量预算：

> **约 ¥2,500–3,000。**

主要成本仍会是：

- 访谈人员
- 交通
- 编辑
- 摄影/扫描
- 书籍设计
- 印刷装订

---

## 66. 基础云资源

初期部署：

```text
API Server
4C8G

PostgreSQL
2C4G

Redis
1–2GB

Object Storage

CDN 暂不需要
GPU 不需要
```

所有模型走API，因此服务器无需GPU。

小规模阶段月基础设施预算：

> **约 ¥500–1,500/月**

具体取决于云厂商、数据库是否托管以及备份策略。

---

## 67. 项目代码结构

```text
memoir-copilot/
│
├── desktop/
│   ├── src/
│   └── src-tauri/
│       ├── audio/
│       ├── storage/
│       ├── asr/
│       └── sync/
│
├── backend/
│   ├── api/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   │   ├── analysis/
│   │   ├── state/
│   │   ├── transcription/
│   │   └── audio/
│   ├── workers/
│   └── prompts/
│
├── shared/
│   ├── schemas/
│   └── event-types/
│
└── infrastructure/
    ├── docker/
    └── deployment/
```

---

## 68. 开发阶段

### Phase 1 — Audio Core

完成：

- 外置麦克风
- 音频设备选择
- 多轨录音
- Chunk
- FLAC
- Crash Recovery
- 音量检测
- 本地SQLite

### Phase 2 — Live Transcript

完成：

- Tencent WebSocket
- Speaker diarization
- Partial/Final transcript
- Transcript UI
- 搜索
- 音频跳转

### Phase 3 — Structured AI

完成：

- Interview State
- Luna Analyzer
- JSON Schema
- Evidence
- State Delta
- State Merge

### Phase 4 — Interview Copilot

完成：

- 动态问题
- Coverage
- Open Loop
- 人物
- 事件
- 时间轴
- First Experience

### Phase 5 — Global Intelligence

完成：

- Terra Analyzer
- Timeline Gap
- Person Gap
- Event Gap
- Conflict
- 30分钟检查

### Phase 6 — End Review

完成：

- Sol Final Review
- 准备收尾
- Top 3–8 Questions
- 覆盖报告

### Phase 7 — Dual Recording

完成：

- Watch导入
- Sync Tone
- Clock Drift
- Audio Alignment
- Tencent离线ASR
- OpenAI离线ASR
- Transcript Diff
- Conflict resolution

### Phase 8 — Final Archive

完成：

- Canonical Transcript
- Clean Transcript
- Final Replay
- Final Interview State
- PDF/Word/export接口

---

## 69. 必须达到的验收指标

### 音频

连续：

**4小时无人工干预录音。**

程序异常：

> 已落盘音频不可丢失。

目标最大损失：

**<5秒。**

### 网络

断网：

**至少30分钟仍能完整记录。**

网络恢复：

自动补处理。

### 实时字幕

目标延迟：

**<2–3秒。**

### AI分析

10分钟窗口触发后：

目标：

**1分钟内完成State更新。**

### Evidence

要求：

**100% AI事实必须带 source_segment_id。**

无Evidence：

不能写入正式Event。

### 日期

明确日期提取：

目标 Precision：

**≥95%。**

模糊日期：

不得擅自精确化。

### 人物/事件抽取

在人工标注测试集中：

目标 Precision：

**≥90%。**

宁愿漏掉，也不能乱编。

### 问题覆盖

访谈者人工判断：

推荐问题有效率目标：

**≥80%。**

### Post Transcript

正式稿中的：

- 人名
- 地名
- 年份
- 金额

必须进入重点复核机制。

---

## 70. MVP最终范围

第一版**不要做回忆录生成器**。

MVP只做：

1. 长时间可靠录音
2. 实时Speaker ASR
3. 实时Transcript
4. 10分钟结构化分析
5. 动态问题
6. 人物/事件
7. 实时时间线
8. Open Loop
9. 人生第一次
10. 30分钟Gap Analysis
11. 结束前检查
12. Apple Watch导入
13. 双ASR校准
14. Final Transcript
15. Final Interview State

做到这里就已经是一个完整、独立、有明确商业价值的产品。

---

## 71. 最终推荐技术组合

```text
Desktop
Tauri 2
Vue 3
TypeScript
Rust
CPAL
FFmpeg
SQLite / SQLCipher

Realtime ASR
Tencent ASR V2
16k_zh_en_speaker_2.0

Backend
FastAPI
PostgreSQL
Redis
Celery
COS / OSS / S3

AI
OpenAI Responses API

10min
GPT-5.6 Luna

30min
GPT-5.6 Terra

Final
GPT-5.6 Sol

Offline Watch ASR
GPT-Transcribe

Primary Offline ASR
Tencent File ASR 2.0

Architecture
Local-first
Event-driven
Event Sourcing
Structured Output
Evidence-first
Provider abstraction
```

---

## 72. V1 技术立项基线

第一阶段只开发采访端，不碰自动成书。

全部工程目标集中在：

> **录得住、转得快、理得清、提醒准、最后校得回来。**

这是 V1 的核心验收标准。
