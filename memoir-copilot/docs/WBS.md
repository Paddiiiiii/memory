# V1 WBS（初版人日估算）

假设：1 名全栈工程师熟悉 Tauri/FastAPI。人日为约数。

| 里程碑 | 内容 | 人日 |
|--------|------|------|
| M0 | Rust 双轨录音、Chunk FLAC、Crash recovery、SQLite/SQLCipher、健康监控、Sync tone | 12 |
| M1 | 腾讯实时 ASR 签票+WSS、Speaker map、Transcript UI、搜索/跳转 | 10 |
| M2 | Schema/Prompt/Merge/Window Analyzer/Evidence | 10 |
| M3 | 问题库、评分、建议 UI、Open Loop、First Experience | 8 |
| M4 | Terra Global、Gap、准备收尾 Sol | 6 |
| M5 | Watch 导入、对齐、双 ASR、冲突队列 | 14 |
| M6 | Canonical/Clean、Final Replay、Subject Merge、导出 | 10 |
| 横切 | Auth/Audit/Docker/OpenAPI/测试/手册/CI | 10 |
| **合计** | | **~80** |

Critical Path：M0 → M1 → M2 → M3 → M5 → M6（M4 可与 M3 部分并行）

Alpha：M0+M1+M2 可演示  
Beta：M0–M6 + 真实样本评估
