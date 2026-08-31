# Memoir Copilot

老人回忆录实时访谈 Copilot — V1 工程仓库。

## 结构

| 目录 | 说明 |
|------|------|
| `desktop/` | Tauri 2 + Vue 3 采访端 |
| `backend/` | FastAPI + Celery + PostgreSQL |
| `shared/` | JSON Schema 与事件类型 |
| `seeds/` | 问题库 / Prompt / Taxonomy |
| `infrastructure/` | Docker Compose |
| `docs/` | 部署与操作手册 |

## 当前实现进度（非完成）

已具备：Backend API（Auth/Project/Session/Transcript/State/Export/Media/Postprocess/Markers）、Merge/Scoring/双ASR对齐算法单测、Vue 采访端骨架、Tauri 音频合同、Seeds、Docker 编排文件。

**P1 进度（本机）：**
- ✅ Docker Desktop + PostgreSQL + Redis
- ✅ Alembic 0001/0002 + bootstrap admin
- ✅ API 联调：登录 → 建项目 → Consent → Session → stub transcript → finishing → 导出（`python -m scripts.p1_smoke`）
- ✅ Rustc/Cargo 1.98 + VS Build Tools C++
- ✅ `memoir-audio-core`：60s FLAC Chunk + checksum + recovery_manifest（`memoir-audio-cli sine 65` 已验证 2 chunks）
- ✅ cpal 设备枚举 / 单轨录音实现已编译；当前 Agent 环境 WASAPI **无输入设备**，真机麦验证待你本机交互会话执行
- ✅ 采访页主路径改为 Tauri 原生录音（拒绝浏览器 getUserMedia）

真机录音验证：
```bash
cd desktop/src-tauri/crates/audio-core
cargo run --bin memoir-audio-cli -- devices
cargo run --bin memoir-audio-cli -- record 65 g:/memory/audio_test_out
```

## 快速开始（开发）

### Backend

```bash
cd backend
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run python -m scripts.bootstrap_admin
uv run uvicorn app.main:app --reload --port 8000
```

### Celery

```bash
cd backend
uv run celery -A app.workers.celery_app worker -l info
```

### Desktop（前端 UI，可先不编 Rust）

```bash
cd desktop
pnpm install
pnpm dev
```

### 全栈 Docker

```bash
cd infrastructure/docker
docker compose up -d
```

## 文档

- 技术方案：仓库根目录上级 `老人回忆录实时访谈Copilot_技术方案_V1.0.md`
- 决策附录：`V1_Decision_Register_Addendum_01.md`
- 开发基线：`V1_开发基线.md`

## License

Private. See `THIRD_PARTY_LICENSES`（待生成 SBOM）。
