# Memoir Copilot · 老人回忆录实时访谈助手

SaaS 后端 + Tauri 桌面端：边采边录、实时字幕（腾讯 ASR）、现场 AI 建议、会后导出。

仓库主工程在 [`memoir-copilot/`](./memoir-copilot/)。

## 填密钥即可用（最短路径）

### 1. 准备密钥

| 密钥 | 是否必须 | 作用 |
|------|----------|------|
| `OPENAI_API_KEY` | 云端 AI 建议时必须 | 窗口分析 / 收尾建议（兼容 `OPENAI_BASE_URL`） |
| `TENCENT_ASR_APP_ID` + `SECRET_ID` + `SECRET_KEY` | 实时字幕时必须 | [腾讯云实时语音识别](https://cloud.tencent.com/document/product/1093/48982) |
| `COS_*` | 可选 | 不填则媒体存本地 `backend/.data/media` |

不勾选「云端 AI」Consent 时，可**零密钥**完成本地录音 → 标记/笔记 → 导出。

### 2. 配置环境

```bash
cd memoir-copilot/backend
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY / TENCENT_ASR_* （及可选 COS）
```

### 3. 启动基础设施 + API

**方式 A — Docker（推荐）**

```bash
cd memoir-copilot/infrastructure/docker
docker compose up -d --build
# 健康检查
curl http://127.0.0.1:8000/health
```

**方式 B — 本机**

```bash
# 先起 PostgreSQL 16 + Redis 7（或只用 compose 起这两项）
cd memoir-copilot/backend
uv sync
uv run alembic upgrade head
uv run python -m scripts.bootstrap_admin
uv run python -m scripts.seed_prompts
uv run uvicorn app.main:app --reload --port 8000

# 另开终端：Celery（云端分析需要）
uv run celery -A app.workers.celery_app.celery_app worker -l info
```

默认管理员（首次登录后请改密）：

- 邮箱：`admin@example.com`
- 密码：`ChangeMeAdmin123!`

### 4. 启动桌面端（录音必须用 Tauri）

```bash
cd memoir-copilot/desktop
cp .env.example .env   # 可选，默认已指向 http://127.0.0.1:8000
pnpm install
pnpm tauri:dev
```

> 仅 `pnpm dev`（浏览器）**不能录音**。P1 主路径是 Tauri + cpal 原生采集。

### 5. 使用流程

1. 登录 → 新建项目 → 勾选 Consent A（录音）；需要字幕/AI 再勾选 Consent B  
2. 「开始访谈准备」→ 选择麦克风 → 「开始采访」  
3. 有腾讯 ASR 密钥且勾选 B 时，实时字幕会推到画面并上报后端  
4. 结束采访 → 导出 JSON / SRT  

## 目录

| 路径 | 说明 |
|------|------|
| `memoir-copilot/backend` | FastAPI + Celery + Alembic |
| `memoir-copilot/desktop` | Tauri 2 + Vue 3 采访端 |
| `memoir-copilot/seeds` | 问题库 / Prompt / Taxonomy |
| `memoir-copilot/shared` | JSON Schema / 事件类型 |
| `memoir-copilot/infrastructure/docker` | Compose 全栈 |
| `老人回忆录实时访谈Copilot_技术方案_V1.0.md` | 产品技术方案 |
| `V1_开发基线.md` / `V1_Decision_Register_Addendum_01.md` | 冻结决策 |

## 能力边界（诚实说明）

已可用：登录、项目/Consent、Session、原生录音（60s FLAC + recovery）、腾讯实时 ASR 签票与桌面推流、问题库建议、标记/笔记、导出 JSON/SRT/VTT/MD/TXT、窗口/全局/收尾 LLM（填 OpenAI Key）、Docker 一键起栈。

仍偏骨架 / 后续迭代：Watch 双 ASR 真转写、COS 生产上传、会后文件 ASR 对齐、SQLCipher 本地 outbox、完整 CI/SBOM。

## 文档

- 工程说明：[`memoir-copilot/README.md`](./memoir-copilot/README.md)
- 部署：[`memoir-copilot/docs/部署手册.md`](./memoir-copilot/docs/部署手册.md)
- 采访操作：[`memoir-copilot/docs/采访者操作手册.md`](./memoir-copilot/docs/采访者操作手册.md)

## License

Private.
