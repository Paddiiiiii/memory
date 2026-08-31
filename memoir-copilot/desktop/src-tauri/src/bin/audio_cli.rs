//! Standalone M0 verifier (no Tauri UI): list devices / record N seconds / print health.
use memoir_copilot_lib::audio::engine::Recorder;
use std::env;
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

fn main() {
    let mut args = env::args().skip(1);
    let cmd = args.next().unwrap_or_else(|| "help".into());
    match cmd.as_str() {
        "devices" => match Recorder::list_input_devices() {
            Ok(list) => {
                for d in list {
                    println!("{}{}", if d.is_default { "* " } else { "  " }, d.name);
                }
            }
            Err(e) => {
                eprintln!("error: {e}");
                std::process::exit(1);
            }
        },
        "record" => {
            let secs: u64 = args
                .next()
                .and_then(|s| s.parse().ok())
                .unwrap_or(65);
            let dir = args
                .next()
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("audio_test_out"));
            println!("recording {secs}s → {}", dir.display());
            let rec = match Recorder::start(dir.clone(), None) {
                Ok(r) => r,
                Err(e) => {
                    eprintln!("start failed: {e}");
                    std::process::exit(1);
                }
            };
            let start = std::time::Instant::now();
            while start.elapsed() < Duration::from_secs(secs) {
                thread::sleep(Duration::from_secs(1));
                let h = rec.health();
                println!(
                    "t={}s active_ms={} rms={:.1}dBFS peak={:.1}dBFS level={} {}",
                    start.elapsed().as_secs(),
                    rec.active_ms(),
                    h.rms_dbfs,
                    h.peak_dbfs,
                    h.level,
                    h.message
                );
            }
            match rec.stop() {
                Ok(m) => {
                    println!("stopped. chunks={} active_ms={}", m.chunks.len(), m.active_recording_ms);
                    for c in m.chunks {
                        println!(" - {} {}..{} ms sha256={}", c.path, c.start_ms, c.end_ms, &c.checksum[..12]);
                    }
                    println!("manifest written under {}", dir.display());
                }
                Err(e) => {
                    eprintln!("stop failed: {e}");
                    std::process::exit(1);
                }
            }
        }
        _ => {
            eprintln!("usage:");
            eprintln!("  memoir-audio-cli devices");
            eprintln!("  memoir-audio-cli record [seconds=65] [outdir=audio_test_out]");
        }
    }
}
