import { AsrApi, SessionApi } from "./api";
import { drainPcmForAsr } from "./nativeAudio";

export type AsrHandlers = {
  onPartial: (text: string) => void;
  onFinal: (seg: {
    speaker: string;
    startMs: number;
    endMs: number;
    text: string;
    sequence: number;
  }) => void;
  onError?: (err: string) => void;
};

function b64ToArrayBuffer(b64: string): ArrayBuffer {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

/**
 * Tencent realtime ASR: ticket → WSS → stream PCM from native recorder → POST finals.
 * Requires Consent B + TENCENT_ASR_* keys on backend.
 */
export class TencentLiveAsr {
  private ws: WebSocket | null = null;
  private timer: number | undefined;
  private seq = 0;
  private stopped = false;
  private voiceId = crypto.randomUUID().replace(/-/g, "").slice(0, 16);

  constructor(
    private sessionId: string,
    private handlers: AsrHandlers,
  ) {}

  async start() {
    this.stopped = false;
    const ticket = await AsrApi.realtimeTicket(this.sessionId, this.voiceId);
    const url = ticket.wss_url;
    if (!url) throw new Error("ASR ticket 缺少 wss_url");

    await new Promise<void>((resolve, reject) => {
      const ws = new WebSocket(url);
      this.ws = ws;
      ws.binaryType = "arraybuffer";
      const timeout = window.setTimeout(() => reject(new Error("ASR WSS 连接超时")), 15_000);
      ws.onopen = () => {
        window.clearTimeout(timeout);
        resolve();
      };
      ws.onerror = () => {
        window.clearTimeout(timeout);
        reject(new Error("ASR WSS 连接失败"));
      };
      ws.onmessage = (ev) => this.onMessage(ev);
      ws.onclose = () => {
        if (!this.stopped) this.handlers.onError?.("ASR 连接已关闭");
      };
    });

    this.timer = window.setInterval(() => {
      void this.pump();
    }, 200);
  }

  private async pump() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      const chunk = await drainPcmForAsr(3200); // ~200ms @16k
      if (!chunk.samples || !chunk.pcm_base64) return;
      this.ws.send(b64ToArrayBuffer(chunk.pcm_base64));
    } catch {
      /* not recording / empty */
    }
  }

  private async onMessage(ev: MessageEvent) {
    if (typeof ev.data !== "string") return;
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(ev.data) as Record<string, unknown>;
    } catch {
      return;
    }
    const code = msg.code ?? msg.ret_code;
    if (code !== undefined && Number(code) !== 0) {
      this.handlers.onError?.(String(msg.message || msg.err_msg || `ASR error ${code}`));
      return;
    }
    const result = (msg.result as Record<string, unknown>) || msg;
    const text = String(result.voice_text_str || result.text || "").trim();
    if (!text) return;
    const sliceType = Number(result.slice_type ?? result.final ?? 0);
    // slice_type: 0=start, 1=partial, 2=final (tencent); some packs use final=1
    const isFinal = sliceType === 2 || result.final === 1 || result.final === true;
    if (!isFinal) {
      this.handlers.onPartial(text);
      return;
    }
    this.handlers.onPartial("");
    const startMs = Math.floor(Number(result.start_time || result.begin_time || 0));
    const endMs = Math.floor(Number(result.end_time || startMs + 1000));
    const speaker = String(result.speaker || result.speaker_id || "speaker_0");
    const sequence = ++this.seq;
    this.handlers.onFinal({ speaker, startMs, endMs, text, sequence });
    try {
      await SessionApi.postSegment(this.sessionId, {
        sequence_number: sequence,
        speaker_id: speaker,
        start_ms: startMs,
        end_ms: endMs,
        raw_text: text,
        confidence: typeof result.confidence === "number" ? result.confidence : undefined,
        source: "tencent_live",
      });
    } catch (e) {
      this.handlers.onError?.(e instanceof Error ? e.message : String(e));
    }
  }

  async stop() {
    this.stopped = true;
    if (this.timer) window.clearInterval(this.timer);
    this.timer = undefined;
    const ws = this.ws;
    this.ws = null;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: "end" }));
      } catch {
        /* ignore */
      }
      ws.close();
    }
  }
}
