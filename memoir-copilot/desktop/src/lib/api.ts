const BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  must_change_password: boolean;
};

function authHeaders(): HeadersInit {
  const access = localStorage.getItem("access_token");
  return access ? { Authorization: `Bearer ${access}` } : {};
}

async function tryRefresh(): Promise<boolean> {
  const refresh = localStorage.getItem("refresh_token");
  if (!refresh) return false;
  const r = await fetch(`${BASE}/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh, device_id: localStorage.getItem("device_id") }),
  });
  if (!r.ok) return false;
  const data = (await r.json()) as TokenPair;
  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);
  return true;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...authHeaders(),
    ...(init.headers || {}),
  };
  let res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    const ok = await tryRefresh();
    if (ok) {
      res = await fetch(`${BASE}${path}`, {
        ...init,
        headers: { ...headers, ...authHeaders() },
      });
    }
  }
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const AuthApi = {
  login(email: string, password: string) {
    if (!localStorage.getItem("device_id")) {
      localStorage.setItem("device_id", crypto.randomUUID());
    }
    return api<TokenPair>("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        device_id: localStorage.getItem("device_id"),
      }),
    });
  },
  me() {
    return api<{ id: string; email: string; role: string; display_name: string; must_change_password: boolean }>(
      "/v1/auth/me",
    );
  },
};

export const ProjectApi = {
  list() {
    return api<Array<{ id: string; title: string; subject?: { display_name: string } }>>("/v1/projects");
  },
  create(title: string, displayName: string) {
    return api("/v1/projects", {
      method: "POST",
      body: JSON.stringify({
        title,
        subject: { display_name: displayName, preferred_address: displayName },
      }),
    });
  },
  consent(projectId: string, consent_type: string, granted: boolean) {
    return api(`/v1/projects/${projectId}/consents`, {
      method: "POST",
      body: JSON.stringify({ consent_type, granted }),
    });
  },
};

export const SessionApi = {
  create(projectId: string, title = "") {
    return api<{ id: string }>(`/v1/projects/${projectId}/sessions`, {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  },
  ready(sessionId: string) {
    return api(`/v1/sessions/${sessionId}/ready`, { method: "POST" });
  },
  start(sessionId: string) {
    return api(`/v1/sessions/${sessionId}/start`, { method: "POST" });
  },
  pause(sessionId: string) {
    return api(`/v1/sessions/${sessionId}/pause`, { method: "POST" });
  },
  finish(sessionId: string) {
    return api(`/v1/sessions/${sessionId}/finish`, { method: "POST" });
  },
  finishingComplete(sessionId: string, recovery_manifest: Record<string, unknown>, active_recording_ms: number) {
    return api(`/v1/sessions/${sessionId}/finishing-complete`, {
      method: "POST",
      body: JSON.stringify({ recovery_manifest, active_recording_ms }),
    });
  },
  get(sessionId: string) {
    return api<{ id: string; status: string; cloud_processing_enabled: boolean; active_recording_ms: number }>(
      `/v1/sessions/${sessionId}`,
    );
  },
  state(sessionId: string, which: "live" | "final" = "live") {
    return api<{ version: number; state: Record<string, unknown> }>(
      `/v1/sessions/${sessionId}/state?which=${which}`,
    );
  },
  suggestions(sessionId: string) {
    return api<Array<{ id: string; text: string; score: number }>>(`/v1/sessions/${sessionId}/suggestions`);
  },
  questionAction(sessionId: string, question_id: string, action: string) {
    return api(`/v1/sessions/${sessionId}/questions/actions`, {
      method: "POST",
      body: JSON.stringify({ question_id, action }),
    });
  },
  postSegment(
    sessionId: string,
    body: {
      sequence_number: number;
      speaker_id: string;
      start_ms: number;
      end_ms: number;
      raw_text: string;
      confidence?: number;
      source?: string;
    },
  ) {
    return api(`/v1/sessions/${sessionId}/transcript/segments`, {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": `seg-${body.sequence_number}` },
    });
  },
  finalReview(sessionId: string) {
    return api(`/v1/sessions/${sessionId}/analysis/final`, { method: "POST" });
  },
  exportUrl(sessionId: string, format: "json" | "srt" | "vtt" | "markdown" | "txt", layer?: string) {
    const q = layer ? `?layer=${layer}` : "";
    return `${BASE}/v1/sessions/${sessionId}/export/${format}${q}`;
  },
};

export const AsrApi = {
  realtimeTicket(sessionId: string, voiceId: string) {
    return api<{
      wss_url: string;
      expire_at: number;
      sample_rate: number;
      voice_id: string;
      engine_model_type: string;
    }>("/v1/asr/realtime-ticket", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, voice_id: voiceId }),
    });
  },
};

export { BASE as API_BASE };
