from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.paths import prompts_dir
from app.models import AnalysisRun, InterviewSession, PromptVersion, TranscriptSegment
from app.providers.llm import LLMProvider, get_llm_provider
from app.providers.model_registry import resolve_model
from app.services.state.merge import apply_delta, empty_interview_state, validate_delta_evidence
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(coro):
    return asyncio.run(coro)


async def _resolve_prompt(db, prompt_name: str, fallback: str) -> str:
    result = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.prompt_name == prompt_name, PromptVersion.active.is_(True))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row and row.prompt_text:
        return row.prompt_text
    seeds = prompts_dir()
    if seeds.exists():
        for path in seeds.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if data.get("prompt_name") == prompt_name and data.get("prompt_text"):
                return data["prompt_text"]
    return fallback


async def _load_segments(session_id, start_ms: int, end_ms: int) -> list[TranscriptSegment]:
    async with SessionLocal() as db:
        result = await db.execute(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.session_id == session_id,
                TranscriptSegment.start_ms >= start_ms,
                TranscriptSegment.end_ms <= end_ms,
            )
            .order_by(TranscriptSegment.sequence_number)
        )
        return list(result.scalars().all())


def _window_bounds(end_ms: int) -> tuple[int, int]:
    # Trigger points every 10 min of active recording; input last 12 min except first
    end = (end_ms // 600_000) * 600_000
    if end < 600_000:
        return 0, max(end_ms, 0)
    start = max(0, end - 720_000)  # 12 minutes
    return start, end


@celery_app.task(name="maybe_enqueue_window_analysis", bind=True, max_retries=3)
def maybe_enqueue_window_analysis(self, session_id: str, end_ms: int) -> None:
    if end_ms < 600_000:
        return
    # Fire near multiples of 10 minutes (within 15s slack of segment end)
    boundary = (end_ms // 600_000) * 600_000
    if abs(end_ms - boundary) > 15_000 and end_ms % 600_000 > 15_000:
        # only enqueue when crossing boundary roughly
        prev = ((end_ms - 1) // 600_000) * 600_000
        if prev == boundary:
            return
    enqueue_window_analysis.delay(session_id, end_ms)


@celery_app.task(name="enqueue_window_analysis", bind=True, max_retries=3, default_retry_delay=2)
def enqueue_window_analysis(self, session_id: str, end_ms: int) -> dict[str, Any]:
    try:
        return _run(_run_window(session_id, end_ms))
    except Exception as exc:  # noqa: BLE001
        countdown = [0, 2, 8][min(self.request.retries, 2)]
        raise self.retry(exc=exc, countdown=countdown) from exc


async def _run_window(session_id: str, end_ms: int) -> dict[str, Any]:
    settings = get_settings()
    start_ms, win_end = _window_bounds(end_ms)
    async with SessionLocal() as db:
        from uuid import UUID

        session = await db.get(InterviewSession, UUID(session_id))
        if session is None or not session.cloud_processing_enabled:
            return {"skipped": True}
        segs = await _load_segments(UUID(session_id), start_ms, win_end if win_end else end_ms)
        known = {str(s.id) for s in segs}
        texts = [
            {
                "segment_id": str(s.id),
                "speaker_id": s.speaker_id,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "text": s.edited_text or s.raw_text,
            }
            for s in segs
        ]
        resolved = resolve_model("WINDOW_ANALYZER")
        llm: LLMProvider = get_llm_provider()
        prompt = await _resolve_prompt(
            db,
            "WINDOW_ANALYZER",
            "You are WINDOW_ANALYZER. Return JSON StateDelta only. "
            "Every fact must include evidence segment_ids. No chain-of-thought.",
        )
        raw = await llm.structured(
            model=resolved.model_id,
            reasoning_effort=resolved.reasoning_effort,
            system=prompt,
            user={
                "window": {"start_ms": start_ms, "end_ms": win_end or end_ms},
                "state": session.live_state,
                "transcript": texts,
            },
        )
        delta = raw if isinstance(raw, dict) else {}
        validated = validate_delta_evidence(delta, known) if known else delta
        run = AnalysisRun(
            session_id=session.id,
            analyzer="WINDOW_ANALYZER",
            provider=resolved.provider,
            model_id=resolved.model_id,
            model_snapshot=resolved.model_snapshot,
            prompt_version="WINDOW_ANALYZER_v1",
            schema_version="state_delta_v1",
            reasoning_effort=resolved.reasoning_effort,
            state_version_in=session.live_state_version,
            input_segment_ids=list(known),
            raw_output=raw if isinstance(raw, dict) else {"raw": raw},
            validated_output=validated,
            success=validated is not None,
            error=None if validated is not None else "evidence_invalid_ratio",
        )
        if validated is not None:
            new_state = apply_delta(session.live_state or empty_interview_state("session_live"), validated)
            session.live_state = new_state
            session.live_state_version = int(new_state.get("version") or session.live_state_version + 1)
            run.state_version_out = session.live_state_version
        db.add(run)
        await db.commit()
        # global every 30 min
        if (win_end or end_ms) > 0 and (win_end or end_ms) % 1_800_000 < 60_000:
            enqueue_global_analysis.delay(session_id)
        return {"success": run.success, "version": session.live_state_version}


@celery_app.task(name="enqueue_global_analysis", bind=True, max_retries=3)
def enqueue_global_analysis(self, session_id: str) -> dict[str, Any]:
    try:
        return _run(_run_named(session_id, "GLOBAL_ANALYZER", "GLOBAL_ANALYZER_v1", "medium"))
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=[0, 2, 8][min(self.request.retries, 2)]) from exc


@celery_app.task(name="enqueue_final_review", bind=True, max_retries=3)
def enqueue_final_review(self, session_id: str) -> dict[str, Any]:
    try:
        return _run(_run_named(session_id, "FINAL_REVIEW", "FINAL_COVERAGE_v1", "high"))
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=[0, 2, 8][min(self.request.retries, 2)]) from exc


async def _run_named(session_id: str, role: str, prompt_version: str, effort: str) -> dict[str, Any]:
    from uuid import UUID

    async with SessionLocal() as db:
        session = await db.get(InterviewSession, UUID(session_id))
        if session is None or not session.cloud_processing_enabled:
            return {"skipped": True}
        resolved = resolve_model(role)
        llm = get_llm_provider()
        prompt = await _resolve_prompt(
            db,
            role if role != "FINAL_REVIEW" else "FINAL_COVERAGE",
            f"You are {role}. Return JSON findings/suggestions only. Evidence required. No CoT.",
        )
        # seed file uses FINAL_COVERAGE naming; also try FINAL_REVIEW
        if prompt.startswith("You are ") and role == "FINAL_REVIEW":
            prompt = await _resolve_prompt(db, "FINAL_REVIEW", prompt)
        raw = await llm.structured(
            model=resolved.model_id,
            reasoning_effort=effort or resolved.reasoning_effort,
            system=prompt,
            user={"state": session.live_state},
        )
        run = AnalysisRun(
            session_id=session.id,
            analyzer=role,
            provider=resolved.provider,
            model_id=resolved.model_id,
            prompt_version=prompt_version,
            schema_version="v1",
            reasoning_effort=effort,
            state_version_in=session.live_state_version,
            raw_output=raw if isinstance(raw, dict) else {"raw": raw},
            validated_output=raw if isinstance(raw, dict) else None,
            success=isinstance(raw, dict),
        )
        # Attach suggestions into coverage for FINAL
        if role == "FINAL_REVIEW" and isinstance(raw, dict):
            state = dict(session.live_state or {})
            coverage = dict(state.get("coverage") or {})
            coverage["closing_questions"] = raw.get("questions") or raw.get("suggestions") or []
            coverage["closing_cached_at_ms"] = session.active_recording_ms
            state["coverage"] = coverage
            if raw.get("gaps"):
                state["gaps"] = list(state.get("gaps") or []) + list(raw["gaps"])
            session.live_state = state
            session.live_state_version = int(session.live_state_version or 0) + 1
            run.state_version_out = session.live_state_version
        db.add(run)
        await db.commit()
        return {"success": run.success}


@celery_app.task(name="enqueue_session_processing", bind=True, max_retries=5)
def enqueue_session_processing(self, session_id: str) -> dict[str, Any]:
    """Post-interview pipeline stub: file ASR / align / replay / subject merge — all retryable."""
    try:
        return _run(_post_process(session_id))
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=30) from exc


async def _post_process(session_id: str) -> dict[str, Any]:
    from uuid import UUID

    from app.models import SessionStatus, Subject
    from app.services.state.merge import merge_subject_canonical

    async with SessionLocal() as db:
        session = await db.get(InterviewSession, UUID(session_id))
        if session is None:
            return {"skipped": True}
        # Placeholder: copy live → final then merge subject (real dual-ASR later)
        if not session.final_state or session.final_state.get("version", 0) <= 1:
            final = dict(session.live_state or empty_interview_state("session_final"))
            final["scope"] = "session_final"
            session.final_state = final
            session.final_state_version = int(final.get("version") or 1)
        subject = await db.get(Subject, session.subject_id)
        if subject is not None:
            subject.canonical_state = merge_subject_canonical(
                subject.canonical_state or {}, session.final_state or {}
            )
        session.status = SessionStatus.COMPLETED.value
        session.postprocess_quality = "single_source"  # until watch imported
        await db.commit()
        return {"status": session.status}
