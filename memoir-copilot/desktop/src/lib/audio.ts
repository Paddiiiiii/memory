/**
 * Browser-dev audio capture shim.
 * On Tauri + Rust, replace with invoke('audio_*') calling cpal/FLAC chunk writer.
 */
export type AudioChunkMeta = {
  chunk_id: string;
  track_id: "primary" | "safety";
  start_ms: number;
  end_ms: number;
  sample_rate: number;
  channels: number;
};

export class BrowserRecorder {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null;
  private startedAt = 0;
  onLevel?: (rms: number) => void;
  onChunk?: (meta: AudioChunkMeta, pcm: Float32Array) => void;

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.ctx = new AudioContext({ sampleRate: 48000 });
    const source = this.ctx.createMediaStreamSource(this.stream);
    this.processor = this.ctx.createScriptProcessor(4096, 1, 1);
    this.startedAt = performance.now();
    let chunkStart = 0;
    let buffer: number[] = [];
    const chunkSamples = 48000; // ~1s accumulate demo; prod Rust uses 60s FLAC

    this.processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      let sum = 0;
      for (let i = 0; i < input.length; i++) {
        const v = input[i];
        sum += v * v;
        buffer.push(v);
      }
      const rms = Math.sqrt(sum / input.length);
      this.onLevel?.(rms);
      if (buffer.length >= chunkSamples) {
        const pcm = Float32Array.from(buffer.splice(0, chunkSamples));
        const start_ms = chunkStart;
        const end_ms = chunkStart + 1000;
        chunkStart = end_ms;
        this.onChunk?.(
          {
            chunk_id: crypto.randomUUID(),
            track_id: "primary",
            start_ms,
            end_ms,
            sample_rate: 48000,
            channels: 1,
          },
          pcm,
        );
      }
    };
    source.connect(this.processor);
    this.processor.connect(this.ctx.destination);
  }

  async stop() {
    this.processor?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    await this.ctx?.close();
    this.processor = null;
    this.stream = null;
    this.ctx = null;
  }
}

/** Sync tone: linear chirp 1200→2200 Hz, 250ms, -12 dBFS, 10ms fades */
export async function playSyncTone() {
  const ctx = new AudioContext({ sampleRate: 48000 });
  const duration = 0.25;
  const frames = Math.floor(ctx.sampleRate * duration);
  const buffer = ctx.createBuffer(1, frames, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  const f0 = 1200;
  const f1 = 2200;
  const amp = Math.pow(10, -12 / 20);
  const fade = Math.floor(ctx.sampleRate * 0.01);
  for (let i = 0; i < frames; i++) {
    const t = i / ctx.sampleRate;
    const f = f0 + (f1 - f0) * (t / duration);
    let a = amp;
    if (i < fade) a *= i / fade;
    if (i > frames - fade) a *= (frames - i) / fade;
    data[i] = a * Math.sin(2 * Math.PI * f * t);
  }
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  src.connect(ctx.destination);
  src.start();
  await new Promise((r) => setTimeout(r, duration * 1000 + 30));
  await ctx.close();
}
