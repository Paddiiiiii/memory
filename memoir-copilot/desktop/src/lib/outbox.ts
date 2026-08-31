/**
 * Browser/dev local outbox (IndexedDB via localStorage fallback).
 * Tauri/SQLCipher will replace persistence; API contract stays the same.
 */
export type OutboxEvent = {
  id: string;
  session_id: string;
  sequence_number: number;
  type: string;
  payload: unknown;
  created_at: number;
  status: "pending" | "sent" | "failed";
};

const KEY = "memoir_outbox_v1";

function readAll(): OutboxEvent[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]") as OutboxEvent[];
  } catch {
    return [];
  }
}

function writeAll(items: OutboxEvent[]) {
  localStorage.setItem(KEY, JSON.stringify(items));
}

export const LocalOutbox = {
  enqueue(partial: Omit<OutboxEvent, "id" | "created_at" | "status">) {
    const items = readAll();
    const ev: OutboxEvent = {
      ...partial,
      id: crypto.randomUUID(),
      created_at: Date.now(),
      status: "pending",
    };
    items.push(ev);
    writeAll(items);
    return ev;
  },
  pending() {
    return readAll().filter((e) => e.status === "pending");
  },
  markSent(id: string) {
    const items = readAll().map((e) => (e.id === id ? { ...e, status: "sent" as const } : e));
    writeAll(items);
  },
  markFailed(id: string) {
    const items = readAll().map((e) => (e.id === id ? { ...e, status: "failed" as const } : e));
    writeAll(items);
  },
  async flush(send: (ev: OutboxEvent) => Promise<void>) {
    for (const ev of this.pending()) {
      try {
        await send(ev);
        this.markSent(ev.id);
      } catch {
        this.markFailed(ev.id);
      }
    }
  },
};
