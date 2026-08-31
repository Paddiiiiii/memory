//! Audio health: clipping / silence thresholds from V1 baseline.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HealthLevel {
    Ok,
    Warn,
    Critical,
}

pub fn evaluate_rms_dbfs(rms_dbfs: f32, silence_secs: f32, both_tracks_low_secs: f32) -> HealthLevel {
    if both_tracks_low_secs >= 30.0 {
        return HealthLevel::Critical;
    }
    if rms_dbfs < -55.0 && silence_secs >= 20.0 {
        return HealthLevel::Warn;
    }
    HealthLevel::Ok
}

pub fn clipping_ratio_alert(peak_dbfs: f32, clip_ratio_in_3s: f32) -> bool {
    peak_dbfs > -1.0 && clip_ratio_in_3s > 0.005
}
