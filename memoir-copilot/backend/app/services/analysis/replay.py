from __future__ import annotations

from typing import Any


def slice_windows(active_ms: int, step_ms: int = 600_000, window_ms: int = 720_000) -> list[tuple[int, int]]:
    """Return (start,end) windows on active recording timeline for Final Replay."""
    if active_ms <= 0:
        return [(0, 0)]
    ends = list(range(step_ms, active_ms + step_ms, step_ms))
    if ends[-1] < active_ms:
        ends.append(((active_ms + step_ms - 1) // step_ms) * step_ms)
    windows: list[tuple[int, int]] = []
    for end in ends:
        end = min(end, active_ms)
        if end <= step_ms:
            windows.append((0, end))
        else:
            windows.append((max(0, end - window_ms), end))
        if end >= active_ms:
            break
    return windows


def build_replay_plan(session: dict[str, Any]) -> dict[str, Any]:
    active = int(session.get("active_recording_ms") or 0)
    windows = slice_windows(active)
    return {
        "session_id": session.get("id"),
        "active_recording_ms": active,
        "stages": [
            {"name": "Luna", "role": "WINDOW_ANALYZER", "windows": [{"start_ms": s, "end_ms": e} for s, e in windows]},
            {"name": "Terra", "role": "GLOBAL_ANALYZER", "every_ms": 1_800_000},
            {"name": "Sol", "role": "FINAL_REVIEW", "once": True},
        ],
        "output_scope": "session_final",
    }
