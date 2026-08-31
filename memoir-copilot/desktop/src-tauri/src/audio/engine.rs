//! M0 audio engine: cpal capture → 60s FLAC chunks → health metrics → crash recovery.
//! Windows P1: single primary track. Dual-track later on macOS.

use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use flacenc::component::BitRepr;
use flacenc::error::Verify;
use sha2::{Digest, Sha256};
use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Error)]
pub enum AudioError {
    #[error("no input device")]
    NoInputDevice,
    #[error("device: {0}")]
    Device(String),
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("flac: {0}")]
    Flac(String),
    #[error("not recording")]
    NotRecording,
    #[error("{0}")]
    Other(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceInfo {
    pub name: String,
    pub is_default: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChunkMeta {
    pub chunk_id: String,
    pub track_id: String,
    pub index: u64,
    pub start_ms: u64,
    pub end_ms: u64,
    pub sample_rate: u32,
    pub channels: u16,
    pub checksum: String,
    pub path: String,
    pub sync_status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthSnapshot {
    pub rms_dbfs: f32,
    pub peak_dbfs: f32,
    pub clipping: bool,
    pub silence: bool,
    pub level: String,
    pub message: String,
    pub sample_rate: u32,
    pub underrun: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecoveryManifest {
    pub session_dir: String,
    pub track_id: String,
    pub sample_rate: u32,
    pub chunks: Vec<ChunkMeta>,
    pub last_flush_ms: u64,
    pub active_recording_ms: u64,
    pub crashed_part: Option<String>,
}

struct SharedState {
    samples: VecDeque<f32>,
    writing: bool,
}

pub struct Recorder {
    stop: Arc<AtomicBool>,
    active_ms: Arc<AtomicU64>,
    health: Arc<Mutex<HealthSnapshot>>,
    meta: Arc<Mutex<Vec<ChunkMeta>>>,
    join: Option<JoinHandle<Result<(), AudioError>>>,
    stream: Option<cpal::Stream>,
    session_dir: PathBuf,
    sample_rate: u32,
}

impl Recorder {
    pub fn list_input_devices() -> Result<Vec<DeviceInfo>, AudioError> {
        let host = cpal::default_host();
        let default_name = host
            .default_input_device()
            .and_then(|d| d.name().ok())
            .unwrap_or_default();
        let mut out = Vec::new();
        let devices = host.input_devices().map_err(|e| AudioError::Device(e.to_string()))?;
        for d in devices {
            let name = d.name().unwrap_or_else(|_| "unknown".into());
            let is_default = name == default_name;
            out.push(DeviceInfo { name, is_default });
        }
        if out.is_empty() {
            return Err(AudioError::NoInputDevice);
        }
        Ok(out)
    }

    pub fn start(session_dir: PathBuf, device_name: Option<String>) -> Result<Self, AudioError> {
        fs::create_dir_all(&session_dir)?;
        let host = cpal::default_host();
        let device = if let Some(name) = device_name {
            host.input_devices()
                .map_err(|e| AudioError::Device(e.to_string()))?
                .find(|d| d.name().ok().as_deref() == Some(name.as_str()))
                .ok_or(AudioError::NoInputDevice)?
        } else {
            host.default_input_device().ok_or(AudioError::NoInputDevice)?
        };

        let config = device
            .default_input_config()
            .map_err(|e| AudioError::Device(e.to_string()))?;
        let sample_rate = config.sample_rate().0;
        let channels = config.channels() as usize;

        let stop = Arc::new(AtomicBool::new(false));
        let active_ms = Arc::new(AtomicU64::new(0));
        let health = Arc::new(Mutex::new(HealthSnapshot {
            rms_dbfs: -120.0,
            peak_dbfs: -120.0,
            clipping: false,
            silence: false,
            level: "ok".into(),
            message: String::new(),
            sample_rate,
            underrun: false,
        }));
        let meta = Arc::new(Mutex::new(Vec::new()));
        let shared = Arc::new(Mutex::new(SharedState {
            samples: VecDeque::new(),
            writing: true,
        }));

        let shared_cb = Arc::clone(&shared);
        let health_cb = Arc::clone(&health);
        let active_cb = Arc::clone(&active_ms);
        let err_fn = |e| eprintln!("cpal stream error: {e}");

        let stream = match config.sample_format() {
            cpal::SampleFormat::F32 => device.build_input_stream(
                &config.into(),
                move |data: &[f32], _| {
                    push_samples(&shared_cb, &health_cb, &active_cb, data, channels, sample_rate);
                },
                err_fn,
                None,
            ),
            cpal::SampleFormat::I16 => device.build_input_stream(
                &config.into(),
                move |data: &[i16], _| {
                    let f: Vec<f32> = data.iter().map(|s| *s as f32 / i16::MAX as f32).collect();
                    push_samples(&shared_cb, &health_cb, &active_cb, &f, channels, sample_rate);
                },
                err_fn,
                None,
            ),
            cpal::SampleFormat::U16 => device.build_input_stream(
                &config.into(),
                move |data: &[u16], _| {
                    let f: Vec<f32> = data
                        .iter()
                        .map(|s| (*s as f32 / u16::MAX as f32) * 2.0 - 1.0)
                        .collect();
                    push_samples(&shared_cb, &health_cb, &active_cb, &f, channels, sample_rate);
                },
                err_fn,
                None,
            ),
            other => return Err(AudioError::Device(format!("unsupported format {other:?}"))),
        }
        .map_err(|e| AudioError::Device(e.to_string()))?;

        stream.play().map_err(|e| AudioError::Device(e.to_string()))?;

        let stop_w = Arc::clone(&stop);
        let shared_w = Arc::clone(&shared);
        let meta_w = Arc::clone(&meta);
        let dir_w = session_dir.clone();
        let active_w = Arc::clone(&active_ms);
        let join = thread::spawn(move || {
            writer_loop(stop_w, shared_w, meta_w, dir_w, sample_rate, active_w)
        });

        // recover any leftover .part from previous crash
        let _ = recover_parts(&session_dir, sample_rate);

        Ok(Self {
            stop,
            active_ms,
            health,
            meta,
            join: Some(join),
            stream: Some(stream),
            session_dir,
            sample_rate,
        })
    }

    pub fn health(&self) -> HealthSnapshot {
        self.health.lock().map(|h| h.clone()).unwrap_or(HealthSnapshot {
            rms_dbfs: -120.0,
            peak_dbfs: -120.0,
            clipping: false,
            silence: true,
            level: "critical".into(),
            message: "health lock poisoned".into(),
            sample_rate: self.sample_rate,
            underrun: true,
        })
    }

    pub fn active_ms(&self) -> u64 {
        self.active_ms.load(Ordering::Relaxed)
    }

    pub fn chunks(&self) -> Vec<ChunkMeta> {
        self.meta.lock().map(|m| m.clone()).unwrap_or_default()
    }

    pub fn stop(mut self) -> Result<RecoveryManifest, AudioError> {
        self.stop.store(true, Ordering::SeqCst);
        // drop stream to stop callback
        self.stream.take();
        if let Some(j) = self.join.take() {
            let _ = j.join().map_err(|_| AudioError::Other("writer join failed".into()))?;
        }
        let chunks = self.chunks();
        let manifest = RecoveryManifest {
            session_dir: self.session_dir.to_string_lossy().into(),
            track_id: "primary".into(),
            sample_rate: self.sample_rate,
            chunks: chunks.clone(),
            last_flush_ms: self.active_ms(),
            active_recording_ms: self.active_ms(),
            crashed_part: None,
        };
        let path = self.session_dir.join("recovery_manifest.json");
        fs::write(&path, serde_json::to_string_pretty(&manifest).unwrap())?;
        Ok(manifest)
    }
}

fn push_samples(
    shared: &Arc<Mutex<SharedState>>,
    health: &Arc<Mutex<HealthSnapshot>>,
    active_ms: &Arc<AtomicU64>,
    data: &[f32],
    channels: usize,
    sample_rate: u32,
) {
    // downmix to mono
    let mut mono = Vec::with_capacity(data.len() / channels.max(1) + 1);
    if channels <= 1 {
        mono.extend_from_slice(data);
    } else {
        for frame in data.chunks(channels) {
            let s: f32 = frame.iter().sum::<f32>() / channels as f32;
            mono.push(s);
        }
    }
    let frames = mono.len() as u64;
    let add_ms = frames * 1000 / sample_rate as u64;
    active_ms.fetch_add(add_ms, Ordering::Relaxed);

    // health
    let mut sum = 0.0f32;
    let mut peak = 0.0f32;
    let mut clip = 0usize;
    for &s in &mono {
        let a = s.abs();
        sum += s * s;
        if a > peak {
            peak = a;
        }
        // approx > -1 dBFS
        if a > 0.8912509 {
            clip += 1;
        }
    }
    let n = mono.len().max(1) as f32;
    let rms = (sum / n).sqrt();
    let rms_db = if rms > 1e-9 { 20.0 * rms.log10() } else { -120.0 };
    let peak_db = if peak > 1e-9 { 20.0 * peak.log10() } else { -120.0 };
    let clip_ratio = clip as f32 / n;
    let clipping = peak_db > -1.0 && clip_ratio > 0.005;
    let silence = rms_db < -55.0;

    if let Ok(mut h) = health.lock() {
        // accumulate silence duration via message encoding is crude; keep flags per snapshot
        h.rms_dbfs = rms_db;
        h.peak_dbfs = peak_db;
        h.clipping = clipping;
        h.silence = silence;
        h.sample_rate = sample_rate;
        if clipping {
            h.level = "warn".into();
            h.message = "检测到削波".into();
        } else if silence {
            h.level = "warn".into();
            h.message = "疑似静音".into();
        } else {
            h.level = "ok".into();
            h.message.clear();
        }
    }

    if let Ok(mut st) = shared.lock() {
        if st.writing {
            st.samples.extend(mono);
        }
    }
}

fn writer_loop(
    stop: Arc<AtomicBool>,
    shared: Arc<Mutex<SharedState>>,
    meta: Arc<Mutex<Vec<ChunkMeta>>>,
    session_dir: PathBuf,
    sample_rate: u32,
    active_ms: Arc<AtomicU64>,
) -> Result<(), AudioError> {
    let chunk_samples = sample_rate as usize * 60; // 60 seconds
    let flush_every = Duration::from_secs(2);
    let mut last_flush = Instant::now();
    let mut chunk_index: u64 = 0;
    let mut chunk_start_ms: u64 = 0;
    let mut current: Vec<f32> = Vec::with_capacity(chunk_samples);
    let mut part_path = session_dir.join(format!("primary_{chunk_index:06}.flac.part"));

    while !stop.load(Ordering::SeqCst) {
        // pull samples
        let mut batch = Vec::new();
        if let Ok(mut st) = shared.lock() {
            let take = st.samples.len().min(sample_rate as usize); // ~1s
            batch.extend(st.samples.drain(..take));
        }
        let batch_empty = batch.is_empty();
        if !batch_empty {
            current.extend(batch);
            if last_flush.elapsed() >= flush_every {
                // write partial pcm sidecar for crash recovery (raw f32 little-endian)
                write_part_pcm(&part_path, &current)?;
                last_flush = Instant::now();
            }
        }

        if current.len() >= chunk_samples {
            let chunk: Vec<f32> = current.drain(..chunk_samples).collect();
            let end_ms = chunk_start_ms + 60_000;
            let m = finalize_chunk(
                &session_dir,
                chunk_index,
                chunk_start_ms,
                end_ms,
                sample_rate,
                &chunk,
            )?;
            if let Ok(mut list) = meta.lock() {
                list.push(m);
            }
            chunk_index += 1;
            chunk_start_ms = end_ms;
            part_path = session_dir.join(format!("primary_{chunk_index:06}.flac.part"));
            // remove old part if any leftover name collision
            let _ = fs::remove_file(&part_path);
        }

        if batch_empty {
            thread::sleep(Duration::from_millis(20));
        }
    }

    // finalize remaining (<60s) on stop
    if !current.is_empty() {
        let end_ms = active_ms.load(Ordering::Relaxed).max(chunk_start_ms + 1);
        let m = finalize_chunk(
            &session_dir,
            chunk_index,
            chunk_start_ms,
            end_ms,
            sample_rate,
            &current,
        )?;
        if let Ok(mut list) = meta.lock() {
            list.push(m);
        }
        let _ = fs::remove_file(&part_path);
    }
    Ok(())
}

fn write_part_pcm(path: &Path, samples: &[f32]) -> Result<(), AudioError> {
    let mut f = OpenOptions::new().create(true).write(true).truncate(true).open(path)?;
    for s in samples {
        f.write_all(&s.to_le_bytes())?;
    }
    f.flush()?;
    let _ = f.sync_all();
    Ok(())
}

fn finalize_chunk(
    session_dir: &Path,
    index: u64,
    start_ms: u64,
    end_ms: u64,
    sample_rate: u32,
    samples: &[f32],
) -> Result<ChunkMeta, AudioError> {
    let chunk_id = Uuid::now_v7().to_string();
    let final_name = format!("primary_{index:06}.flac");
    let part = session_dir.join(format!("{final_name}.part"));
    let dest = session_dir.join(&final_name);

    encode_flac_mono(&part, samples, sample_rate)?;
    // atomic-ish rename
    fs::rename(&part, &dest)?;
    // fsync dir entry best-effort
    if let Ok(dir) = File::open(session_dir) {
        let _ = dir.sync_all();
    }

    let bytes = fs::read(&dest)?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    let checksum = format!("{:x}", hasher.finalize());

    let meta = ChunkMeta {
        chunk_id,
        track_id: "primary".into(),
        index,
        start_ms,
        end_ms,
        sample_rate,
        channels: 1,
        checksum,
        path: dest.to_string_lossy().into(),
        sync_status: "local".into(),
    };
    let meta_path = session_dir.join(format!("primary_{index:06}.json"));
    fs::write(meta_path, serde_json::to_string_pretty(&meta).unwrap())?;
    Ok(meta)
}

fn encode_flac_mono(path: &Path, samples: &[f32], sample_rate: u32) -> Result<(), AudioError> {
    use flacenc::component::BitRepr;
    use flacenc::error::Verify;

    // Convert to 24-bit integer PCM for archival quality target
    let mut i32s: Vec<i32> = samples
        .iter()
        .map(|s| {
            let x = s.clamp(-1.0, 1.0);
            (x * 8_388_607.0).round() as i32
        })
        .collect();
    if i32s.is_empty() {
        i32s.push(0);
    }
    let source = flacenc::source::MemSource::from_samples(&i32s, 1, 24, sample_rate as usize);
    let config = flacenc::config::Encoder::default()
        .into_verified()
        .map_err(|e| AudioError::Flac(format!("config: {e:?}")))?;
    let stream = flacenc::encode_with_fixed_block_size(&config, source, config.block_size)
        .map_err(|e| AudioError::Flac(format!("{e:?}")))?;

    let mut sink = flacenc::bitsink::ByteSink::new();
    stream
        .write(&mut sink)
        .map_err(|e| AudioError::Flac(format!("{e:?}")))?;
    let mut f = File::create(path)?;
    f.write_all(sink.as_slice())?;
    f.flush()?;
    let _ = f.sync_all();
    Ok(())
}

/// Try to salvage `.flac.part` PCM leftovers into a recovery flac (best-effort).
pub fn recover_parts(session_dir: &Path, sample_rate: u32) -> Result<Vec<PathBuf>, AudioError> {
    let mut recovered = Vec::new();
    if !session_dir.exists() {
        return Ok(recovered);
    }
    for entry in fs::read_dir(session_dir)? {
        let entry = entry?;
        let path = entry.path();
        let name = path.file_name().and_then(|s| s.to_str()).unwrap_or("");
        if name.ends_with(".flac.part") && !name.contains(".flac.part.") {
            // our writer stores raw f32 in *.flac.part during recording; try decode
            let bytes = fs::read(&path)?;
            if bytes.len() < 4 || bytes.len() % 4 != 0 {
                let _ = fs::remove_file(&path);
                continue;
            }
            let mut samples = Vec::with_capacity(bytes.len() / 4);
            for chunk in bytes.chunks_exact(4) {
                samples.push(f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]));
            }
            let salvage = session_dir.join(format!(
                "recovered_{}.flac",
                Uuid::now_v7().to_string().chars().take(8).collect::<String>()
            ));
            if encode_flac_mono(&salvage, &samples, sample_rate).is_ok() {
                recovered.push(salvage);
            }
            let _ = fs::remove_file(&path);
        }
    }
    Ok(recovered)
}
