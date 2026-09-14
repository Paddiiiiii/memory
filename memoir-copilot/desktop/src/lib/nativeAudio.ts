import { invoke } from "@tauri-apps/api/core";

export type DeviceInfo = { name: string; is_default: boolean };
export type HealthSnapshot = {
  rms_dbfs: number;
  peak_dbfs: number;
  clipping: boolean;
  silence: boolean;
  level: string;
  message: string;
  sample_rate: number;
  underrun: boolean;
};
export type RecoveryManifest = {
  session_dir: string;
  track_id: string;
  sample_rate: number;
  chunks: Array<{
    chunk_id: string;
    path: string;
    start_ms: number;
    end_ms: number;
    checksum: string;
  }>;
  active_recording_ms: number;
};

export type PcmChunk = {
  sample_rate: number;
  pcm_base64: string;
  samples: number;
};

export function isTauri(): boolean {
  return typeof window !== "undefined" && !!(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
}

export async function listAudioDevices(): Promise<DeviceInfo[]> {
  return invoke("list_audio_devices");
}

export async function startNativeRecording(sessionId: string, deviceName?: string): Promise<string> {
  return invoke("start_recording", { sessionId, deviceName: deviceName ?? null });
}

export async function stopNativeRecording(): Promise<RecoveryManifest> {
  return invoke("stop_recording");
}

export async function nativeHealth(): Promise<HealthSnapshot> {
  return invoke("recording_health");
}

export async function nativeActiveMs(): Promise<number> {
  return invoke("recording_active_ms");
}

export async function drainPcmForAsr(maxSamples = 16000): Promise<PcmChunk> {
  return invoke("drain_pcm_for_asr", { maxSamples });
}
