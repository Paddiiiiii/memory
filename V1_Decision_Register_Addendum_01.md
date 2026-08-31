# V1 Decision Register Addendum 01

**标题：** Auth / Session / Toolchain / Canonical Merge  
**状态：** 已冻结（Frozen）  
**生效范围：** V1 全部工程实现  
**上位文档：** 《老人回忆录实时访谈 Copilot 技术方案 V1.0》+ 《V1 开发问题统一答复》  
**冻结日期：** 2026-08-28

本附录对上一轮「微决策」及直接相关工程约束做最终冻结。实现必须以本文件为准；与技术方案冲突时，以本附录为准。

---

## A. 十项微决策（最终结论）

### A1. Token 有效期与旋转

| 项 | 值 |
|---|---|
| Access Token | 15 分钟 |
| Refresh Token | 30 天 |
| Rotation | 每次 refresh 后旧 refresh token **立即失效** |
| 存储 | 服务器只存 refresh token 的 **hash** + session family；**不存明文** |
| 复用检测 | 已旋转 token 被再次使用 → **整条 token family 作废**，要求重新登录 |

Access Token **不必**单独存 DB，依赖最多 15 分钟自然过期。高安全操作可额外检查 `token_version`。

### A2. 密码重置

- V1 **不做** forgot-password UI、邮件验证码。
- 仅 **Admin CLI / Admin API** 执行 reset。
- 重置后：强制用户下次登录修改密码（`must_change_password = true`）。
- 密码修改或管理员强制重置后：该 User **所有现存 Refresh Session 全部失效**。

### A3. 首个 Admin（Bootstrap）

- Seed 从环境变量读取，例如：
  - `BOOTSTRAP_ADMIN_EMAIL`
  - `BOOTSTRAP_ADMIN_PASSWORD`
- **必须 idempotent**：已存在同邮箱用户时 **不得覆盖密码**。
- 生产首次创建后，应移除 bootstrap password 环境变量。

### A4. `draft → ready`

进入 `ready` 条件：

1. Subject **必填字段完整**
2. Consent **RECORDING（Consent A）** 已确认 `granted=true`

Consent **CLOUD_AI_PROCESSING（Consent B）**：

- **不影响**进入 `ready`
- 只决定 `cloud_processing_enabled`
- `false` 时 UI 明确显示：**「仅本地录音模式」**

### A5. `finishing → processing`（本地完成优先）

流程：

```text
用户结束采访
  → 二次确认
  → finishing
      ├─ stop input
      ├─ SYNC_END
      ├─ encoder flush
      ├─ finalize audio chunks
      ├─ checksum
      ├─ SQLite transaction commit
      └─ recovery manifest
  → 确认本地录音完整
  → processing
```

约束：

- **最不能失败的是 `finishing`**
- 云端上传失败 **不能**阻止进入 `processing`；任务进入 outbox / pending 即可
- `processing` 之后全部允许失败与重试（见 B3）

### A6. Windows 开发密钥

- Windows 开发态优先 **DPAPI**
- 禁止自行设计密码学方案
- 加密文件仅作 **dev fallback**
- 正式 macOS：**Keychain only**

### A7. UI 库

- Vue 3 + **自定义基础组件**
- 允许少量无样式 / headless 工具库
- **禁止**引入 Element Plus 等大型 UI 框架
- 采访页目标：低干扰、稳定、快捷操作

### A8. 包管理与语言版本

| 层 | 工具 |
|---|---|
| Frontend | pnpm |
| Rust | Cargo workspace |
| Python | **3.12 + uv** |

- 统一 `pyproject.toml` + `uv.lock`
- **不要**同时维护 Poetry

### A9. 模型 ID（逻辑角色）

业务代码 **只**使用逻辑角色，例如：

- `WINDOW_ANALYZER_MODEL`
- `GLOBAL_ANALYZER_MODEL`
- `FINAL_REVIEW_MODEL`

具体 provider / model ID 由 **环境配置或 Prompt / Model Registry** 决定。  
业务代码禁止硬编码真实 model string。

### A10. Subject Canonical Merge

```text
Session Final State
        ↓
Subject Merge Engine
        ↓
Subject Canonical State
```

- 任何互斥事实 → **Subject-level Conflict**
- **禁止** last-write-wins
- 详见 B5

---

## B. 直接相关工程约束（一并冻结）

### B1. 认证会话模型

```text
User
 └─ AuthSession
      ├─ refresh_token_family_id
      ├─ device_id
      ├─ created_at
      ├─ expires_at
      ├─ revoked_at
      └─ last_used_at
```

补充：

- Refresh Token = 高熵随机值；DB 只存 hash
- 密码修改 / 管理员强制重置 → 该 User 全部 Refresh Session 失效
- Access Token 可不落库；高安全操作可检查 `token_version`（User 级或 AuthSession 级，实现时选一并文档化）

### B2. Consent 可审计记录（非双 Boolean）

不要只用两个 Boolean。使用可审计 Consent Record：

```json
{
  "consent_type": "RECORDING",
  "granted": true,
  "captured_at": "...",
  "captured_by": "...",
  "method": "verbal_and_operator_confirmed",
  "version": "consent_v1"
}
```

V1 类型：

| Type | 含义 |
|---|---|
| `RECORDING` | Consent A：同意录音（开始 Session 硬门槛） |
| `CLOUD_AI_PROCESSING` | Consent B：同意云端 AI / ASR |

预留扩展（不改表结构）：

- `PUBLICATION`
- `FAMILY_ACCESS`
- `RESEARCH_USE`

### B3. Session 结束：本地完成优先

精确状态链（结束段）：

```text
recording
   ↓
finishing   ← 本地硬保证，不可失败
   ↓
processing  ← 全部可失败、可重试
```

`processing` 内可异步重试的任务：

- cloud upload
- file ASR
- Watch import
- alignment
- canonical transcript
- clean transcript
- final replay
- subject merge

原则：**用户点击结束采访后，最不能失败的是 finishing；最可以异步重试的是 processing。**

### B4. 模型配置两层解析

```text
Environment Default
        ↓
Prompt / Model Registry
        ↓
Runtime Model Resolution
```

环境默认示例：

```text
WINDOW_ANALYZER_MODEL=gpt-5.6-luna
GLOBAL_ANALYZER_MODEL=gpt-5.6-terra
FINAL_REVIEW_MODEL=gpt-5.6-sol
```

每次 `analysis_run` **必须**记录实际执行时的：

- `provider`
- `model_id`
- `model_snapshot` / version（若 provider 提供）
- `prompt_version`
- `schema_version`
- `reasoning_effort`

未来模型升级后，必须能追溯某个 State 由哪一个模型 / Prompt / Schema 产生。

### B5. Canonical State 原则（第 10 条细化）

| 层级 | 含义 |
|---|---|
| Session State | 证据来源（该场访谈内的结构化理解） |
| Subject Canonical State | 跨访谈后的「当前最佳理解」 |
| Canonical ≠ 不可修改真相 | 人工可裁决；历史 Claim 永不删除 |

示例：

```text
Session 1: 结婚年份 = 1972  evidence = S1:seg_182
Session 2: 结婚年份 = 1973  evidence = S2:seg_091

Subject:
  CONFLICT
  ├─ Claim A: 1972
  └─ Claim B: 1973

人工确认后:
  Resolved: 1973
  resolution_source: 受访者第二次确认 + 结婚证照片
  Claim 1972: status = rejected（保留历史，不得删除）
```

规则：

1. 互斥事实 → Conflict，禁止静默覆盖  
2. 人工 Resolved 必须记录 `resolution_source`  
3. 被否决的 Claim **保留历史**，`status = rejected`  
4. **不能删除错误历史证据**

---

## C. 标记

本文件标记为：

> **V1 Decision Register Addendum 01 — Auth / Session / Toolchain / Canonical Merge**

状态：**Frozen**

后续变更必须新开 Addendum（02+），不得静默改写本文件已冻结条款。

---

## D. 实现检查清单（工程对照）

- [ ] AuthSession / refresh family / rotation reuse → revoke family
- [ ] Admin password reset + must_change_password + revoke all sessions
- [ ] Idempotent bootstrap admin seed
- [ ] Consent records（RECORDING / CLOUD_AI_PROCESSING）+ cloud_processing_enabled
- [ ] Session finishing 本地硬路径 + recovery manifest
- [ ] processing 任务全部 outbox / Celery 可重试
- [ ] Windows DPAPI（dev）/ macOS Keychain（prod）
- [ ] Vue 自定义组件；无 Element Plus
- [ ] pnpm + Cargo workspace + Python 3.12 + uv
- [ ] 逻辑模型角色 + Env / Registry 两层解析
- [ ] analysis_run 记录 provider/model/prompt/schema/reasoning
- [ ] Subject Merge + Conflict + rejected Claim 保留
