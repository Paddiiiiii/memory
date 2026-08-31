//! 60s chunk writer contract: write *.flac.part then atomic rename; fsync ~2s.
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChunkMeta {
    pub chunk_id: String,
    pub track_id: String,
    pub start_ms: u64,
    pub end_ms: u64,
    pub sample_rate: u32,
    pub channels: u16,
    pub checksum: String,
    pub sync_status: String,
}

pub struct ChunkWriterPlan {
    pub chunk_duration_ms: u64,
    pub flush_interval_ms: u64,
}

impl Default for ChunkWriterPlan {
    fn default() -> Self {
        Self {
            chunk_duration_ms: 60_000,
            flush_interval_ms: 2_000,
        }
    }
}
