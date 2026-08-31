from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_project
from app.core.database import get_db
from app.models import InterviewSession, SpeakerMapping, TranscriptSegment, TranscriptVersion, User
from app.schemas.api import SpeakerMapIn, TranscriptEditIn, TranscriptSegmentIn
from app.services.auth import service as auth_service
from app.workers.tasks import maybe_enqueue_window_analysis

router = APIRouter(tags=["transcript"])


async def _session(db: AsyncSession, user: User, session_id: UUID) -> InterviewSession:
    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(404, "Session 不存在")
    await get_owned_project(session.project_id, user, db)
    return session


@router.post("/sessions/{session_id}/transcript/segments")
async def upsert_segment(
    session_id: UUID,
    body: TranscriptSegmentIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    session = await _session(db, user, session_id)
    result = await db.execute(
        select(TranscriptSegment).where(
            TranscriptSegment.session_id == session.id,
            TranscriptSegment.sequence_number == body.sequence_number,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {
            "id": str(existing.id),
            "sequence_number": existing.sequence_number,
            "deduped": True,
        }
    seg = TranscriptSegment(
        session_id=session.id,
        sequence_number=body.sequence_number,
        speaker_id=body.speaker_id,
        start_ms=body.start_ms,
        end_ms=body.end_ms,
        raw_text=body.raw_text,
        confidence=body.confidence,
        source=body.source,
    )
    db.add(seg)
    await db.flush()
    await db.commit()
    if session.cloud_processing_enabled:
        maybe_enqueue_window_analysis.delay(str(session.id), body.end_ms)
    return {"id": str(seg.id), "sequence_number": seg.sequence_number, "deduped": False}


@router.get("/sessions/{session_id}/transcript")
async def list_transcript(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    session = await _session(db, user, session_id)
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.session_id == session.id)
        .order_by(TranscriptSegment.sequence_number.asc())
    )
    segs = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "sequence_number": s.sequence_number,
            "speaker_id": s.speaker_id,
            "start_ms": s.start_ms,
            "end_ms": s.end_ms,
            "raw_text": s.raw_text,
            "edited_text": s.edited_text,
            "display_text": s.edited_text or s.raw_text,
            "confidence": s.confidence,
            "version": s.version,
        }
        for s in segs
    ]


@router.patch("/transcript/{segment_id}")
async def edit_transcript(
    segment_id: UUID,
    body: TranscriptEditIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    seg = await db.get(TranscriptSegment, segment_id)
    if seg is None:
        raise HTTPException(404, "segment 不存在")
    await _session(db, user, seg.session_id)
    if body.version != seg.version:
        raise HTTPException(409, "版本冲突，请刷新后重试")
    old = seg.edited_text if seg.edited_text is not None else seg.raw_text
    db.add(
        TranscriptVersion(
            segment_id=seg.id,
            old_text=old,
            new_text=body.edited_text,
            edited_by=user.id,
            reason=body.reason,
        )
    )
    seg.edited_text = body.edited_text
    seg.version += 1
    await auth_service.write_audit(
        db,
        actor_id=user.id,
        action="edit_transcript",
        resource_type="transcript_segment",
        resource_id=str(seg.id),
        meta={"reason": body.reason, "version": seg.version},
    )
    await db.commit()
    return {"id": str(seg.id), "version": seg.version, "edited_text": seg.edited_text}


@router.put("/sessions/{session_id}/speakers")
async def map_speaker(
    session_id: UUID,
    body: SpeakerMapIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, user, session_id)
    result = await db.execute(
        select(SpeakerMapping).where(
            SpeakerMapping.session_id == session.id,
            SpeakerMapping.speaker_id == body.speaker_id,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.display_name = body.display_name
        row.role_label = body.role_label
    else:
        db.add(
            SpeakerMapping(
                session_id=session.id,
                speaker_id=body.speaker_id,
                display_name=body.display_name,
                role_label=body.role_label,
            )
        )
    await db.commit()
    return {"ok": True}


@router.get("/sessions/{session_id}/speakers")
async def list_speakers(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    session = await _session(db, user, session_id)
    result = await db.execute(select(SpeakerMapping).where(SpeakerMapping.session_id == session.id))
    return [
        {"speaker_id": r.speaker_id, "display_name": r.display_name, "role_label": r.role_label}
        for r in result.scalars().all()
    ]
