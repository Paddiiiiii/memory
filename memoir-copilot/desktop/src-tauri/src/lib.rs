pub mod audio {
    pub use memoir_audio_core::*;
}
mod storage;

use once_cell::sync::Lazy;
use parking_lot::Mutex;
use tauri::{AppHandle, Manager};

use memoir_audio_core::engine::{DeviceInfo, HealthSnapshot, Recorder, RecoveryManifest};

struct AudioState {
    recorder: Mutex<Option<Recorder>>,
}

static AUDIO: Lazy<AudioState> = Lazy::new(|| AudioState {
    recorder: Mutex::new(None),
});

#[tauri::command]
fn ping() -> String {
    "pong".into()
}

#[tauri::command]
fn sync_tone_spec() -> serde_json::Value {
    audio::sync_tone::spec_json()
}

#[tauri::command]
fn list_audio_devices() -> Result<Vec<DeviceInfo>, String> {
    Recorder::list_input_devices().map_err(|e| e.to_string())
}

#[tauri::command]
fn start_recording(
    app: AppHandle,
    session_id: String,
    device_name: Option<String>,
) -> Result<String, String> {
    let mut guard = AUDIO.recorder.lock();
    if guard.is_some() {
        return Err("already recording".into());
    }
    let base = app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?
        .join("sessions")
        .join(&session_id)
        .join("audio");
    std::fs::create_dir_all(&base).map_err(|e| e.to_string())?;
    let _ = audio::engine::recover_parts(&base, 48000);
    let rec = Recorder::start(base.clone(), device_name).map_err(|e| e.to_string())?;
    *guard = Some(rec);
    Ok(base.to_string_lossy().into())
}

#[tauri::command]
fn recording_health() -> Result<HealthSnapshot, String> {
    let guard = AUDIO.recorder.lock();
    let rec = guard.as_ref().ok_or_else(|| "not recording".to_string())?;
    Ok(rec.health())
}

#[tauri::command]
fn recording_active_ms() -> Result<u64, String> {
    let guard = AUDIO.recorder.lock();
    let rec = guard.as_ref().ok_or_else(|| "not recording".to_string())?;
    Ok(rec.active_ms())
}

#[tauri::command]
fn stop_recording() -> Result<RecoveryManifest, String> {
    let mut guard = AUDIO.recorder.lock();
    let rec = guard.take().ok_or_else(|| "not recording".to_string())?;
    rec.stop().map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![
            ping,
            sync_tone_spec,
            list_audio_devices,
            start_recording,
            recording_health,
            recording_active_ms,
            stop_recording
        ])
        .setup(|app| {
            let _ = app.path().app_data_dir();
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
