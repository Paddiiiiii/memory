<template>
  <div class="interview">
    <div v-if="store.health === 'warn'" class="banner-warn">{{ store.healthMessage || "音频告警" }}</div>
    <div v-if="store.health === 'critical'" class="banner-danger">{{ store.healthMessage || "音频严重告警" }}</div>
    <div v-if="store.localOnly" class="banner-warn">仅本地录音模式 — 云端 ASR / AI 已关闭</div>
    <div v-if="asrError" class="banner-warn">ASR: {{ asrError }}</div>

    <header class="top">
      <div class="rec">
        <span class="dot" :class="{ on: store.status === 'recording' }" />
        <strong>{{ store.status === "recording" ? "REC" : store.status.toUpperCase() }}</strong>
        <span class="time">{{ store.formatMs(store.activeMs) }}</span>
      </div>
      <label class="device" v-if="useNative">
        麦克风
        <select v-model="selectedDevice" :disabled="store.status === 'recording'">
          <option value="">系统默认</option>
          <option v-for="d in devices" :key="d.name" :value="d.name">
            {{ d.name }}{{ d.is_default ? "（默认）" : "" }}
          </option>
        </select>
      </label>
      <div class="meter">
        MIC
        <div class="bar"><i :style="{ width: Math.min(100, store.micLevel * 400) + '%' }" /></div>
      </div>
      <div class="btns">
        <button v-if="store.status === 'idle' || store.status === 'paused'" class="danger" @click="onStart">
          {{ store.status === "paused" ? "继续" : "开始采访" }}
        </button>
        <button v-if="store.status === 'recording'" @click="onPause">暂停</button>
        <button @click="addMarker">添加标记 ⌘M</button>
        <button @click="addNote">笔记 ⌘N</button>
        <button @click="onChangeDirection">换个方向</button>
        <button @click="onClosing">准备收尾</button>
        <button @click="onExport('json')">导出 JSON</button>
        <button @click="onExport('srt')">导出 SRT</button>
        <button class="danger" v-if="store.status === 'recording' || store.status === 'paused'" @click="onFinish">
          结束采访
        </button>
      </div>
    </header>

    <main class="grid">
      <section class="transcript">
        <h2>实时文字稿</h2>
        <div ref="scroller" class="scroll" @scroll="onScroll">
          <article v-for="s in store.segments" :key="s.id" class="seg">
            <time>{{ store.formatMs(s.startMs) }}</time>
            <b>{{ s.speaker }}</b>
            <p>{{ s.text }}</p>
          </article>
          <p v-if="store.partialText" class="partial">{{ store.partialText }}</p>
          <p v-if="!store.segments.length && !store.partialText" class="muted">
            {{ store.localOnly ? "本地模式不会出实时字幕；结束后可导出标记/笔记。" : "开始采访后将显示实时字幕…" }}
          </p>
        </div>
        <button v-if="!stickBottom" class="jump" @click="jumpBottom">↓ 回到实时</button>
      </section>

      <aside class="suggest">
        <h2>当前建议</h2>
        <ol>
          <li v-for="(q, i) in store.suggestions" :key="q.id || i">
            <span>{{ q.text }}</span>
            <small v-if="q.score != null">{{ q.score.toFixed(2) }}</small>
          </li>
        </ol>
        <p v-if="!store.suggestions.length" class="muted">暂无推荐（需问题库或云端分析）</p>
      </aside>

      <section class="questions">
        <h2>动态问题清单</h2>
        <div class="q-list">
          <div v-for="q in visibleQuestions" :key="q.id" class="q-item">
            <div class="q-text">{{ q.text || q.prompt || q.id }}</div>
            <div class="q-actions">
              <button @click="doQuestionAction(q.id, 'pin')">置顶</button>
              <button @click="doQuestionAction(q.id, 'asked')">已问</button>
              <button @click="doQuestionAction(q.id, 'later')">稍后</button>
              <button @click="doQuestionAction(q.id, 'ignore')">忽略</button>
            </div>
          </div>
          <p v-if="!visibleQuestions.length" class="muted">问题库将在创建 Session 时自动载入</p>
        </div>
      </section>

      <aside class="side">
        <nav>
          <button :class="{ on: store.sidebarTab === 'timeline' }" @click="store.sidebarTab = 'timeline'">时间线</button>
          <button :class="{ on: store.sidebarTab === 'people' }" @click="store.sidebarTab = 'people'">人物</button>
          <button :class="{ on: store.sidebarTab === 'loops' }" @click="store.sidebarTab = 'loops'">没说完</button>
          <button :class="{ on: store.sidebarTab === 'questions' }" @click="store.sidebarTab = 'questions'">问题</button>
        </nav>
        <div class="panel">
          <template v-if="store.sidebarTab === 'timeline'">
            <div v-for="(t, i) in timeline" :key="i" class="tl">
              <span>{{ t.earliest || "?" }}</span> {{ t.title }}
            </div>
            <p v-if="!timeline.length" class="muted">事件将显示在此</p>
          </template>
          <template v-else-if="store.sidebarTab === 'people'">
            <div v-for="p in people" :key="p.id">{{ p.name }} <small>{{ p.relationship }}</small></div>
            <p v-if="!people.length" class="muted">人物抽取后显示</p>
          </template>
          <template v-else-if="store.sidebarTab === 'loops'">
            <div v-for="l in loops" :key="l.id" class="loop">{{ l.quote || l.id }}</div>
            <p v-if="!loops.length" class="muted">开放话题</p>
          </template>
          <template v-else>
            <div v-for="q in visibleQuestions.slice(0, 12)" :key="'s-' + q.id" class="tl">
              {{ q.text || q.prompt || q.id }}
            </div>
          </template>
        </div>
      </aside>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useInterviewStore } from "../stores/interview";
import { API_BASE, SessionApi } from "../lib/api";
import { playSyncTone } from "../lib/audio";
import { LocalOutbox } from "../lib/outbox";
import { TencentLiveAsr } from "../lib/tencentAsr";
import {
  isTauri,
  listAudioDevices,
  nativeActiveMs,
  nativeHealth,
  startNativeRecording,
  stopNativeRecording,
  type DeviceInfo,
} from "../lib/nativeAudio";

const props = defineProps<{ sessionId: string }>();
const store = useInterviewStore();
const stickBottom = ref(true);
const scroller = ref<HTMLElement | null>(null);
const statePayload = ref<Record<string, unknown>>({});
const audioDir = ref("");
const useNative = isTauri();
const devices = ref<DeviceInfo[]>([]);
const selectedDevice = ref("");
const asrError = ref("");
let seq = 0;
let healthTimer: number | undefined;
let stateTimer: number | undefined;
let asr: TencentLiveAsr | null = null;

const timeline = computed(() => (statePayload.value.timeline as Array<Record<string, string>>) || []);
const people = computed(() => (statePayload.value.people as Array<Record<string, string>>) || []);
const loops = computed(() => (statePayload.value.open_loops as Array<Record<string, string>>) || []);
const visibleQuestions = computed(() => {
  const qs = (statePayload.value.questions as Array<Record<string, unknown>>) || [];
  return qs
    .filter((q) => !q.session_ignored && q.status !== "asked")
    .slice(0, 40) as Array<Record<string, string>>;
});

async function refreshState() {
  try {
    const s = await SessionApi.get(props.sessionId);
    store.localOnly = !s.cloud_processing_enabled;
    const st = await SessionApi.state(props.sessionId, "live");
    statePayload.value = st.state || {};
    store.suggestions = await SessionApi.suggestions(props.sessionId);
  } catch {
    /* offline ok for local UI */
  }
}

async function startAsrIfNeeded() {
  asrError.value = "";
  if (store.localOnly) return;
  try {
    asr = new TencentLiveAsr(props.sessionId, {
      onPartial: (t) => {
        store.partialText = t;
      },
      onFinal: (seg) => {
        store.segments.push({
          id: crypto.randomUUID(),
          speaker: seg.speaker,
          startMs: seg.startMs,
          endMs: seg.endMs,
          text: seg.text,
        });
        if (stickBottom.value) jumpBottom();
      },
      onError: (e) => {
        asrError.value = e;
      },
    });
    await asr.start();
  } catch (e) {
    asrError.value = e instanceof Error ? e.message : String(e);
    asr = null;
  }
}

async function onStart() {
  if (!useNative) {
    alert("录音主路径仅支持 Tauri 原生 cpal。请运行 pnpm tauri:dev，不要用浏览器 getUserMedia。");
    return;
  }
  if (store.status === "idle") {
    await playSyncTone();
  }
  await SessionApi.start(props.sessionId);
  audioDir.value = await startNativeRecording(
    props.sessionId,
    selectedDevice.value || undefined,
  );
  store.status = "recording";
  store.startClock();
  await startAsrIfNeeded();
  healthTimer = window.setInterval(async () => {
    try {
      const h = await nativeHealth();
      const ms = await nativeActiveMs();
      store.activeMs = ms;
      store.elapsedMs = ms;
      store.micLevel = Math.max(0, Math.min(1, (h.rms_dbfs + 60) / 60));
      store.health = h.level === "ok" ? "ok" : h.level === "critical" ? "critical" : "warn";
      store.healthMessage = h.message;
    } catch {
      /* ignore */
    }
  }, 500);
}

async function onPause() {
  store.status = "paused";
  await SessionApi.pause(props.sessionId);
  if (healthTimer) window.clearInterval(healthTimer);
  healthTimer = undefined;
  if (asr) {
    await asr.stop();
    asr = null;
  }
  await stopNativeRecording();
  store.stopClock();
}

async function doQuestionAction(questionId: string, action: string) {
  try {
    await SessionApi.questionAction(props.sessionId, questionId, action);
    await refreshState();
  } catch (e) {
    alert(e instanceof Error ? e.message : String(e));
  }
}

function addMarker() {
  const ts = Math.floor(store.activeMs);
  store.segments.push({
    id: crypto.randomUUID(),
    speaker: "标记",
    startMs: store.activeMs,
    endMs: store.activeMs,
    text: `[KEY_MOMENT @ ${store.formatMs(store.activeMs)}]`,
  });
  LocalOutbox.enqueue({
    session_id: props.sessionId,
    sequence_number: ++seq,
    type: "marker",
    payload: { marker_type: "KEY_MOMENT", timestamp_ms: ts },
  });
  const token = localStorage.getItem("access_token");
  fetch(`${API_BASE}/v1/sessions/${props.sessionId}/markers`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ marker_type: "KEY_MOMENT", timestamp_ms: ts }),
  }).catch(() => undefined);
}

function addNote() {
  const text = window.prompt("采访者笔记（不会与原话混合）");
  if (!text) return;
  const ts = Math.floor(store.activeMs);
  store.segments.push({
    id: crypto.randomUUID(),
    speaker: "笔记",
    startMs: store.activeMs,
    endMs: store.activeMs,
    text,
  });
  LocalOutbox.enqueue({
    session_id: props.sessionId,
    sequence_number: ++seq,
    type: "note",
    payload: { text, timestamp_ms: ts },
  });
  const token = localStorage.getItem("access_token");
  fetch(`${API_BASE}/v1/sessions/${props.sessionId}/notes`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ text, timestamp_ms: ts }),
  }).catch(() => undefined);
}

async function onChangeDirection() {
  await refreshState();
  if (!store.suggestions.length) {
    store.suggestions = [
      { id: "fallback-1", text: "切换到未覆盖 Topic：人生第一次 / 家庭与祖辈", score: 0.5 },
    ];
  }
}

async function onClosing() {
  if (!store.localOnly) {
    await SessionApi.finalReview(props.sessionId);
    await refreshState();
  } else {
    alert("仅本地模式无法调用收尾分析");
  }
}

function onExport(format: "json" | "srt" | "vtt" | "markdown" | "txt") {
  const url = SessionApi.exportUrl(props.sessionId, format);
  const a = document.createElement("a");
  a.target = "_blank";
  const token = localStorage.getItem("access_token");
  fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    .then((r) => r.blob())
    .then((blob) => {
      const obj = URL.createObjectURL(blob);
      a.href = obj;
      a.download = `session_${props.sessionId}.${format === "markdown" ? "md" : format}`;
      a.click();
      URL.revokeObjectURL(obj);
    })
    .catch((e) => alert(String(e)));
}

async function onFinish() {
  if (!confirm("确认结束采访？结束后将完成本地 finishing 硬路径。")) return;
  store.status = "finishing";
  await playSyncTone();
  if (healthTimer) window.clearInterval(healthTimer);
  healthTimer = undefined;
  if (asr) {
    await asr.stop();
    asr = null;
  }
  let manifest: Record<string, unknown> = {
    tracks: ["primary"],
    chunks_finalized: true,
    sync_end_played: true,
    audio_dir: audioDir.value,
  };
  try {
    if (useNative) {
      const m = await stopNativeRecording();
      manifest = {
        ...manifest,
        ...m,
        chunks_finalized: true,
        checksum_ok: true,
      };
    }
  } catch {
    /* already stopped */
  }
  store.stopClock();
  await SessionApi.finish(props.sessionId);
  const done = await SessionApi.finishingComplete(
    props.sessionId,
    manifest,
    Math.floor(store.activeMs),
  );
  store.status = "idle";
  const status = (done as { status?: string })?.status || "done";
  alert(status === "completed" ? "采访已完成（本地模式）" : "已进入 processing（云端任务异步执行）");
}

function onScroll() {
  const el = scroller.value;
  if (!el) return;
  stickBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
}
function jumpBottom() {
  const el = scroller.value;
  if (!el) return;
  el.scrollTop = el.scrollHeight;
  stickBottom.value = true;
}

function onKey(e: KeyboardEvent) {
  if (e.metaKey && e.shiftKey && e.key.toLowerCase() === "r") {
    e.preventDefault();
    if (store.status === "recording" || store.status === "paused") onFinish();
    else onStart();
  }
  if (e.metaKey && e.shiftKey && e.key.toLowerCase() === "p") {
    e.preventDefault();
    if (store.status === "recording") onPause();
    else if (store.status === "paused") onStart();
  }
  if (e.metaKey && e.key.toLowerCase() === "m") {
    e.preventDefault();
    addMarker();
  }
  if (e.metaKey && e.key.toLowerCase() === "n") {
    e.preventDefault();
    addNote();
  }
}

onMounted(async () => {
  await refreshState();
  stateTimer = window.setInterval(() => {
    void refreshState();
  }, 15_000);
  if (useNative) {
    try {
      devices.value = await listAudioDevices();
      const def = devices.value.find((d) => d.is_default);
      if (def) selectedDevice.value = def.name;
    } catch {
      /* no devices in this environment */
    }
  }
  window.addEventListener("keydown", onKey);
});
onUnmounted(() => {
  store.stopClock();
  if (healthTimer) window.clearInterval(healthTimer);
  if (stateTimer) window.clearInterval(stateTimer);
  window.removeEventListener("keydown", onKey);
  if (asr) void asr.stop();
  if (useNative) {
    stopNativeRecording().catch(() => undefined);
  }
});
</script>

<style scoped>
.interview { height: 100%; display: flex; flex-direction: column; min-width: 1280px; }
.top {
  display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
  padding: 0.65rem 1rem; border-bottom: 1px solid var(--line); background: var(--panel);
}
.rec { display: flex; align-items: center; gap: 0.5rem; font-variant-numeric: tabular-nums; }
.device { display: flex; align-items: center; gap: 0.35rem; color: var(--muted); font-size: 0.85rem; }
.device select { max-width: 220px; }
.dot { width: 10px; height: 10px; border-radius: 50%; background: #ccc; }
.dot.on { background: var(--rec); box-shadow: 0 0 0 4px rgba(196,30,58,.15); }
.meter { display: flex; align-items: center; gap: 0.4rem; color: var(--muted); font-size: 0.85rem; }
.bar { width: 120px; height: 8px; background: #eee; border-radius: 4px; overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--accent); }
.btns { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-left: auto; }
.grid {
  flex: 1; display: grid;
  grid-template-columns: 1.4fr 0.9fr; grid-template-rows: 1fr 0.85fr;
  gap: 1px; background: var(--line); min-height: 0;
}
.transcript, .suggest, .questions, .side { background: var(--panel); padding: 0.75rem 1rem; min-height: 0; position: relative; }
.transcript { grid-row: 1 / 3; display: flex; flex-direction: column; }
h2 { font-size: 0.95rem; margin: 0 0 0.5rem; font-weight: 600; }
.scroll { overflow: auto; flex: 1; }
.seg { margin-bottom: 0.85rem; }
.seg time { color: var(--muted); font-size: 0.8rem; margin-right: 0.5rem; }
.seg p { margin: 0.25rem 0 0; line-height: 1.5; }
.partial { color: var(--muted); font-style: italic; }
.jump { position: absolute; bottom: 1rem; left: 50%; transform: translateX(-50%); }
.suggest ol { margin: 0; padding-left: 1.2rem; display: grid; gap: 0.6rem; }
.suggest li { display: flex; justify-content: space-between; gap: 0.5rem; }
.muted { color: var(--muted); font-size: 0.85rem; }
.q-list { overflow: auto; max-height: 100%; display: grid; gap: 0.5rem; }
.q-item { border-bottom: 1px solid var(--line); padding-bottom: 0.4rem; }
.q-text { font-size: 0.9rem; margin-bottom: 0.25rem; }
.q-actions { display: flex; gap: 0.25rem; flex-wrap: wrap; }
.q-actions button { font-size: 0.75rem; padding: 0.15rem 0.4rem; }
.side nav { display: flex; gap: 0.25rem; margin-bottom: 0.5rem; flex-wrap: wrap; }
.side nav button.on { border-color: var(--accent); color: var(--accent); }
.tl, .loop { padding: 0.35rem 0; border-bottom: 1px solid var(--line); font-size: 0.9rem; }
.banner-warn, .banner-danger {
  padding: 0.4rem 1rem; font-size: 0.85rem;
}
.banner-warn { background: #fff7e6; color: #8a5a00; }
.banner-danger { background: #ffe8e8; color: #a11; }
</style>
