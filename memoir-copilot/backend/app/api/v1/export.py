from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_project
from app.core.database import get_db
from app.models import InterviewSession, Project, SpeakerMapping, Subject, TranscriptSegment, User
from app.services.auth import service as auth_service
from app.services.export.formats import (
    build_project_archive,
    segments_to_markdown,
    segments_to_srt,
    segments_to_txt,
    segments_to_vtt,
)

router = APIRouter(tags=["export"])

QUESTION_BANK_PATH = (
    Path(__file__).resolve().parents[4] / "seeds" / "question_bank" / "question_bank_v1.json"
)


async def _session(db: AsyncSession, user: User, session_id: UUID) -> InterviewSession:
    session = await db.get(InterviewSession, session_id)
    if session is None or session.soft_deleted_at is not None:
        raise HTTPException(404, "Session 不存在")
    await get_owned_project(session.project_id, user, db)
    return session


async def _segments(db: AsyncSession, session_id: UUID) -> list[dict[str, Any]]:
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.session_id == session_id)
        .order_by(TranscriptSegment.sequence_number.asc())
    )
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
            "clean_text": (s.edited_text or s.raw_text),  # until cleaner writes dedicated field
            "confidence": s.confidence,
            "version": s.version,
        }
        for s in result.scalars().all()
    ]


async def _speakers(db: AsyncSession, session_id: UUID) -> dict[str, str]:
    result = await db.execute(select(SpeakerMapping).where(SpeakerMapping.session_id == session_id))
    return {r.speaker_id: r.display_name for r in result.scalars().all()}


@router.get("/sessions/{session_id}/export/srt")
async def export_srt(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    session = await _session(db, user, session_id)
    segs = await _segments(db, session.id)
    names = await _speakers(db, session.id)
    await auth_service.write_audit(
        db, actor_id=user.id, action="export", resource_type="session", resource_id=str(session.id), meta={"format": "srt"}
    )
    await db.commit()
    return PlainTextResponse(segments_to_srt(segs, speaker_names=names), media_type="application/x-subrip")


@router.get("/sessions/{session_id}/export/vtt")
async def export_vtt(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    session = await _session(db, user, session_id)
    segs = await _segments(db, session.id)
    names = await _speakers(db, session.id)
    await auth_service.write_audit(
        db, actor_id=user.id, action="export", resource_type="session", resource_id=str(session.id), meta={"format": "vtt"}
    )
    await db.commit()
    return PlainTextResponse(segments_to_vtt(segs, speaker_names=names), media_type="text/vtt")


@router.get("/sessions/{session_id}/export/markdown")
async def export_markdown(
    session_id: UUID,
    layer: str = "canonical",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    if layer not in {"raw", "canonical", "clean"}:
        raise HTTPException(400, "layer 必须是 raw|canonical|clean")
    session = await _session(db, user, session_id)
    segs = await _segments(db, session.id)
    names = await _speakers(db, session.id)
    await auth_service.write_audit(
        db,
        actor_id=user.id,
        action="export",
        resource_type="session",
        resource_id=str(session.id),
        meta={"format": "markdown", "layer": layer},
    )
    await db.commit()
    body = segments_to_markdown(segs, speaker_names=names, title=session.title or "Transcript", layer=layer)
    return PlainTextResponse(body, media_type="text/markdown; charset=utf-8")


@router.get("/sessions/{session_id}/export/txt")
async def export_txt(
    session_id: UUID,
    layer: str = "canonical",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    if layer not in {"raw", "canonical", "clean"}:
        raise HTTPException(400, "layer 必须是 raw|canonical|clean")
    session = await _session(db, user, session_id)
    segs = await _segments(db, session.id)
    names = await _speakers(db, session.id)
    await auth_service.write_audit(
        db,
        actor_id=user.id,
        action="export",
        resource_type="session",
        resource_id=str(session.id),
        meta={"format": "txt", "layer": layer},
    )
    await db.commit()
    return PlainTextResponse(segments_to_txt(segs, speaker_names=names, layer=layer), media_type="text/plain; charset=utf-8")


@router.get("/sessions/{session_id}/export/json")
async def export_json(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    session = await _session(db, user, session_id)
    project = await db.get(Project, session.project_id)
    subject = await db.get(Subject, session.subject_id)
    if project is None or subject is None:
        raise HTTPException(404, "项目或受访者缺失")
    segs = await _segments(db, session.id)
    names = await _speakers(db, session.id)
    archive = build_project_archive(
        project={"id": str(project.id), "title": project.title, "owner_id": str(project.owner_id)},
        subject={
            "id": str(subject.id),
            "display_name": subject.display_name,
            "preferred_address": subject.preferred_address,
            "primary_language": subject.primary_language,
            "dialect_hint": subject.dialect_hint,
            "canonical_state": subject.canonical_state,
        },
        session={
            "id": str(session.id),
            "status": session.status,
            "title": session.title,
            "active_recording_ms": session.active_recording_ms,
            "postprocess_quality": session.postprocess_quality,
            "live_state": session.live_state,
            "final_state": session.final_state,
            "cloud_processing_enabled": session.cloud_processing_enabled,
        },
        segments=segs,
        speakers=names,
    )
    await auth_service.write_audit(
        db, actor_id=user.id, action="export", resource_type="session", resource_id=str(session.id), meta={"format": "json"}
    )
    await db.commit()
    return Response(
        content=json.dumps(archive, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="session_{session.id}.json"'},
    )
