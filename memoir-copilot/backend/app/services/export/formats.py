from __future__ import annotations

from typing import Any


def _display_text(seg: dict[str, Any]) -> str:
    return (seg.get("edited_text") or seg.get("raw_text") or seg.get("display_text") or "").strip()


def _ms_to_srt(ms: int) -> str:
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1000
    milli = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def _ms_to_vtt(ms: int) -> str:
    return _ms_to_srt(ms).replace(",", ".")


def segments_to_srt(
    segments: list[dict[str, Any]],
    *,
    speaker_names: dict[str, str] | None = None,
) -> str:
    names = speaker_names or {}
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        text = _display_text(seg)
        if not text:
            continue
        speaker = names.get(seg.get("speaker_id", ""), seg.get("speaker_id", ""))
        body = f"{speaker}: {text}" if speaker else text
        lines.append(str(i))
        lines.append(f"{_ms_to_srt(int(seg['start_ms']))} --> {_ms_to_srt(int(seg['end_ms']))}")
        lines.append(body)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def segments_to_vtt(
    segments: list[dict[str, Any]],
    *,
    speaker_names: dict[str, str] | None = None,
) -> str:
    names = speaker_names or {}
    lines = ["WEBVTT", ""]
    for seg in segments:
        text = _display_text(seg)
        if not text:
            continue
        speaker = names.get(seg.get("speaker_id", ""), seg.get("speaker_id", ""))
        body = f"{speaker}: {text}" if speaker else text
        lines.append(f"{_ms_to_vtt(int(seg['start_ms']))} --> {_ms_to_vtt(int(seg['end_ms']))}")
        lines.append(body)
        lines.append("")
    return "\n".join(lines)


def segments_to_markdown(
    segments: list[dict[str, Any]],
    *,
    speaker_names: dict[str, str] | None = None,
    title: str = "Transcript",
    layer: str = "canonical",
) -> str:
    names = speaker_names or {}
    out = [f"# {title}", "", f"_layer: {layer}_", ""]
    for seg in segments:
        text = _display_text(seg)
        if layer == "clean" and seg.get("clean_text"):
            text = str(seg["clean_text"]).strip()
        if layer == "raw":
            text = str(seg.get("raw_text") or "").strip()
        if not text:
            continue
        speaker = names.get(seg.get("speaker_id", ""), seg.get("speaker_id", "speaker"))
        start = int(seg.get("start_ms") or 0)
        mm, ss = divmod(start // 1000, 60)
        hh, mm = divmod(mm, 60)
        out.append(f"**{hh:02d}:{mm:02d}:{ss:02d} · {speaker}**")
        out.append("")
        out.append(text)
        out.append("")
    return "\n".join(out)


def segments_to_txt(
    segments: list[dict[str, Any]],
    *,
    speaker_names: dict[str, str] | None = None,
    layer: str = "canonical",
) -> str:
    names = speaker_names or {}
    lines: list[str] = []
    for seg in segments:
        if layer == "clean" and seg.get("clean_text"):
            text = str(seg["clean_text"]).strip()
        elif layer == "raw":
            text = str(seg.get("raw_text") or "").strip()
        else:
            text = _display_text(seg)
        if not text:
            continue
        speaker = names.get(seg.get("speaker_id", ""), seg.get("speaker_id", "speaker"))
        lines.append(f"[{speaker}] {text}")
    return "\n".join(lines) + ("\n" if lines else "")


def build_project_archive(
    *,
    project: dict[str, Any],
    subject: dict[str, Any],
    session: dict[str, Any],
    segments: list[dict[str, Any]],
    speakers: dict[str, str],
    markers: list[dict[str, Any]] | None = None,
    notes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "format": "memoir_project_archive_v1",
        "project": project,
        "subject": {
            **subject,
            # avoid dumping huge binary; canonical state included
        },
        "session": {
            "id": session.get("id"),
            "status": session.get("status"),
            "title": session.get("title"),
            "active_recording_ms": session.get("active_recording_ms"),
            "postprocess_quality": session.get("postprocess_quality"),
            "live_state": session.get("live_state"),
            "final_state": session.get("final_state"),
            "cloud_processing_enabled": session.get("cloud_processing_enabled"),
        },
        "speakers": speakers,
        "transcript_segments": segments,
        "markers": markers or [],
        "notes": notes or [],
    }
