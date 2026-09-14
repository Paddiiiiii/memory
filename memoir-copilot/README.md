# Memoir Copilot（工程目录）

老人回忆录实时访谈 Copilot — 实现仓库。产品级上手说明见仓库根目录 [README.md](../README.md)。

## 结构

| 目录 | 说明 |
|------|------|
| `desktop/` | Tauri 2 + Vue 3 采访端 |
| `backend/` | FastAPI + Celery + PostgreSQL |
| `shared/` | JSON Schema 与事件类型 |
| `seeds/` | 问题库 / Prompt / Taxonomy |
| `infrastructure/` | Docker Compose |
| `docs/` | 部署与操作手册 |

## 填密钥后怎么跑

1. `backend/cp .env.example .env`，填入：
   - **实时字幕**：`TENCENT_ASR_APP_ID` / `TENCENT_ASR_SECRET_ID` / `TENCENT_ASR_SECRET_KEY`
   - **现场 AI**：`OPENAI_API_KEY`（可选改 `OPENAI_BASE_URL` 与模型名）
2. 起栈：`cd infrastructure/docker && docker compose up -d --build`
3. 桌面：`cd desktop && pnpm install && pnpm tauri:dev`
4. 登录 `admin@example.com` / `ChangeMeAdmin123!`，新建项目并勾选 Consent。

## 开发命令

### Backend

```bash
cd backend
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run python -m scripts.bootstrap_admin
uv run python -m scripts.seed_prompts
uv run uvicorn app.main:app --reload --port 8000
```

Celery（注意完整 app 路径）：

```bash
uv run celery -A app.workers.celery_app.celery_app worker -l info
```

单测 / 冒烟：

```bash
uv run pytest
uv run python -m scripts.p1_smoke   # 需 API 已启动
```

### Desktop

```bash
cd desktop
pnpm install
pnpm tauri:dev          # 完整录音 + ASR
# pnpm dev              # 仅 UI，无法原生录音
```

音频 CLI（不经 Tauri）：

```bash
cd desktop/src-tauri/crates/audio-core
cargo run --bin memoir-audio-cli -- devices
cargo run --bin memoir-audio-cli -- sine 65 ./out
cargo run --bin memoir-audio-cli -- record 65 ./out
```

## 关键实现要点

- 腾讯 ASR：服务端签发官方 HMAC-SHA1 `wss_url`；SecretKey 不出服务端；桌面用原生 PCM 推流。
- 录音：cpal → 60s FLAC Chunk + checksum + `recovery_manifest`；同时 ring-buffer 供 ASR。
- 仅本地 Consent：结束会话直接 `completed`，不依赖 Celery。
- 云端 Consent：结束进入 `processing`，worker 合并 Subject Canonical。
- LLM：优先 Chat Completions JSON；无 Key 时 stub 并打日志。

## 文档

- 技术方案 / 基线：仓库根目录 `*.md`
- `docs/部署手册.md` · `docs/采访者操作手册.md` · `docs/openapi.json`
