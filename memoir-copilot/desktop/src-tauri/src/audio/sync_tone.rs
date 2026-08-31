//! Sync tone: Linear Chirp 1200→2200 Hz, 250ms, 48kHz, -12 dBFS, 10ms fade.
use serde_json::json;

pub fn spec_json() -> serde_json::Value {
    json!({
        "type": "linear_chirp",
        "f0_hz": 1200,
        "f1_hz": 2200,
        "duration_ms": 250,
        "sample_rate": 48000,
        "level_dbfs": -12,
        "fade_ms": 10
    })
}

/// Generate mono f32 samples at -12 dBFS.
pub fn generate_chirp(sample_rate: u32) -> Vec<f32> {
    let duration = 0.25_f32;
    let frames = (sample_rate as f32 * duration) as usize;
    let fade = (sample_rate as f32 * 0.01) as usize;
    let amp = 10f32.powf(-12.0 / 20.0);
    let f0 = 1200.0_f32;
    let f1 = 2200.0_f32;
    let mut out = Vec::with_capacity(frames);
    for i in 0..frames {
        let t = i as f32 / sample_rate as f32;
        let f = f0 + (f1 - f0) * (t / duration);
        let mut a = amp;
        if i < fade {
            a *= i as f32 / fade as f32;
        }
        if i + fade > frames {
            a *= (frames - i) as f32 / fade as f32;
        }
        out.push(a * (2.0 * std::f32::consts::PI * f * t).sin());
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn chirp_length() {
        assert_eq!(generate_chirp(48000).len(), 12000);
    }
}
