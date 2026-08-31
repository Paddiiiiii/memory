import { defineStore } from "pinia";
import { ref } from "vue";

export type RecStatus = "idle" | "recording" | "paused" | "finishing";

export const useInterviewStore = defineStore("interview", () => {
  const status = ref<RecStatus>("idle");
  const elapsedMs = ref(0);
  const activeMs = ref(0);
  const micLevel = ref(0);
  const localOnly = ref(false);
  const health = ref<"ok" | "warn" | "critical">("ok");
  const healthMessage = ref("");
  const partialText = ref("");
  const segments = ref<
    Array<{ id: string; speaker: string; startMs: number; endMs: number; text: string }>
  >([]);
  const suggestions = ref<Array<{ id: string; text: string; score?: number }>>([]);
  const sidebarTab = ref<"timeline" | "people" | "loops" | "questions">("questions");

  let timer: number | undefined;
  let lastTick = 0;

  function startClock() {
    lastTick = performance.now();
    timer = window.setInterval(() => {
      const now = performance.now();
      const delta = now - lastTick;
      lastTick = now;
      if (status.value === "recording") {
        elapsedMs.value += delta;
        activeMs.value += delta;
      }
    }, 200);
  }

  function stopClock() {
    if (timer) window.clearInterval(timer);
    timer = undefined;
  }

  function formatMs(ms: number) {
    const s = Math.floor(ms / 1000);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  }

  return {
    status,
    elapsedMs,
    activeMs,
    micLevel,
    localOnly,
    health,
    healthMessage,
    partialText,
    segments,
    suggestions,
    sidebarTab,
    startClock,
    stopClock,
    formatMs,
  };
});
