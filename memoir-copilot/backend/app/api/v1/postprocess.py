from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_project
from app.core.database import get_db
from app.models import InterviewSession, User
from app.services.analysis.replay import build_replay_plan
from app.services.audio.alignment import estimate_from_sync_peaks
from app.services.transcription.dual_asr import compare_block, merge_blocks
from app.workers.tasks import enqueue_session_processing

router = APIRouter(tags=["postprocess"])


async def _session(db: AsyncSession, user: User, session_id: UUID) -> InterviewSession:
    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(404, "Session 不存在")
    await get_owned_project(session.project_id, user, db)
    return session


class WatchImportIn(BaseModel):
    storage_key: str = Field(description="已上传的 Watch 音频对象键或本地路径标记")
    filename: str = ""
    duration_ms: int | None = None


class AlignIn(BaseModel):
    pc_sync_start_ms: float
    pc_sync_end_ms: float
    watch_sync_start_ms: float
    watch_sync_end_ms: float
    residual_offsets_ms: list[float] = []


class DualCompareIn(BaseModel):
    blocks: list[dict]  # [{tencent: str, openai: str}]


@router.post("/sessions/{session_id}/watch-audio")
async def import_watch_audio(
    session_id: UUID,
    body: WatchImportIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, user, session_id)
    manifest = dict(session.recovery_manifest or {})
    manifest["watch_audio"] = {
        "storage_key": body.storage_key,
        "filename": body.filename,
        "duration_ms": body.duration_ms,
        "imported": True,
    }
    session.recovery_manifest = manifest
    session.postprocess_quality = "dual_pending"
    await db.commit()
    return {"ok": True, "postprocess_quality": session.postprocess_quality}


@router.post("/sessions/{session_id}/align")
async def align_tracks(
    session_id: UUID,
    body: AlignIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, user, session_id)
    result = estimate_from_sync_peaks(
        pc_start_ms=body.pc_sync_start_ms,
        pc_end_ms=body.pc_sync_end_ms,
        watch_start_ms=body.watch_sync_start_ms,
        watch_end_ms=body.watch_sync_end_ms,
        residual_offsets_ms=body.residual_offsets_ms,
    )
    manifest = dict(session.recovery_manifest or {})
    manifest["alignment"] = {
        "start_offset_ms": result.start_offset_ms,
        "end_offset_ms": result.end_offset_ms,
        "clock_ratio": result.clock_ratio,
        "confidence": result.confidence,
        "method": result.method,
        "low_confidence": result.low_confidence,
        "residual_offsets_ms": result.residual_offsets_ms,
    }
    session.recovery_manifest = manifest
    await db.commit()
    return manifest["alignment"]


@router.post("/sessions/{session_id}/retranscribe/compare")
async def compare_dual_transcript(
    session_id: UUID,
    body: DualCompareIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, user, session_id)
    verdicts = [
        compare_block(str(b.get("tencent") or ""), str(b.get("openai") or "")) for b in body.blocks
    ]
    merged = merge_blocks(verdicts)
    disputed = [x for x in merged if x["status"] == "DISPUTED"]
    manifest = dict(session.recovery_manifest or {})
    manifest["dual_asr"] = {"blocks": merged, "disputed_count": len(disputed)}
    session.recovery_manifest = manifest
    if disputed:
        session.postprocess_quality = "completed_needs_review"
    else:
        session.postprocess_quality = "dual_confirmed"
    await db.commit()
    return {"blocks": merged, "disputed_count": len(disputed), "postprocess_quality": session.postprocess_quality}


@router.post("/sessions/{session_id}/rebuild")
async def rebuild_final(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, user, session_id)
    plan = build_replay_plan(
        {
            "id": str(session.id),
            "active_recording_ms": session.active_recording_ms,
        }
    )
    if session.cloud_processing_enabled:
        enqueue_session_processing.delay(str(session.id))
    return {"queued": bool(session.cloud_processing_enabled), "plan": plan}
