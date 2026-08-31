from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_project
from app.core.database import get_db
from app.models import ConsentRecord, InterviewSession, SessionStatus, Subject, User, utcnow
from app.schemas.api import SessionCreate, SessionOut
from app.services.auth import service as auth_service
from app.services.state.merge import empty_interview_state
from app.workers.tasks import enqueue_session_processing

router = APIRouter(tags=["sessions"])


class ActiveMsIn(BaseModel):
    active_recording_ms: int


async def _latest_consent(db: AsyncSession, subject_id: UUID, consent_type: str) -> ConsentRecord | None:
    result = await db.execute(
        select(ConsentRecord)
        .where(ConsentRecord.subject_id == subject_id, ConsentRecord.consent_type == consent_type)
        .order_by(ConsentRecord.captured_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_session_for_user(db: AsyncSession, user: User, session_id: UUID) -> InterviewSession:
    session = await db.get(InterviewSession, session_id)
    if session is None or session.soft_deleted_at is not None:
        raise HTTPException(404, "Session 不存在")
    await get_owned_project(session.project_id, user, db)
    return session


@router.post("/projects/{project_id}/sessions", response_model=SessionOut)
async def create_session(
    project_id: UUID,
    body: SessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewSession:
    project = await get_owned_project(project_id, user, db)
    result = await db.execute(select(Subject).where(Subject.project_id == project.id))
    subject = result.scalar_one_or_none()
    if subject is None:
        raise HTTPException(400, "Subject 缺失")

    # Load canonical into live seed
    live = empty_interview_state("session_live")
    canon = subject.canonical_state or {}
    for key in ("people", "places", "events", "questions", "first_experiences", "open_loops", "themes"):
        if canon.get(key):
            live[key] = canon[key]

    # Seed default question bank when subject has no questions yet
    if not live.get("questions"):
        from app.api.v1.media import load_question_bank

        bank = load_question_bank()
        live["questions"] = bank.get("questions") or []
        live["topics"] = bank.get("topics") or []
        live["question_bank_version"] = bank.get("version")

    session = InterviewSession(
        project_id=project.id,
        subject_id=subject.id,
        status=SessionStatus.DRAFT.value,
        title=body.title or f"访谈 {utcnow().date().isoformat()}",
        primary_language=body.primary_language or subject.primary_language,
        dialect_hint=body.dialect_hint or subject.dialect_hint,
        live_state=live,
        final_state=empty_interview_state("session_final"),
        live_state_version=1,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewSession:
    return await _get_session_for_user(db, user, session_id)


@router.post("/sessions/{session_id}/ready", response_model=SessionOut)
async def mark_ready(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewSession:
    session = await _get_session_for_user(db, user, session_id)
    subject = await db.get(Subject, session.subject_id)
    if subject is None or not subject.display_name.strip():
        raise HTTPException(400, "Subject 必填信息不完整")
    recording = await _latest_consent(db, subject.id, "RECORDING")
    if recording is None or not recording.granted:
        raise HTTPException(400, "需要 Consent RECORDING")
    cloud = await _latest_consent(db, subject.id, "CLOUD_AI_PROCESSING")
    session.cloud_processing_enabled = bool(cloud and cloud.granted)
    session.status = SessionStatus.READY.value
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/sessions/{session_id}/start", response_model=SessionOut)
async def start_recording(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewSession:
    session = await _get_session_for_user(db, user, session_id)
    if session.status not in {SessionStatus.READY.value, SessionStatus.PAUSED.value}:
        raise HTTPException(400, f"当前状态不可开始: {session.status}")
    if session.status == SessionStatus.READY.value:
        session.started_at = utcnow()
    session.status = SessionStatus.RECORDING.value
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/sessions/{session_id}/pause", response_model=SessionOut)
async def pause_recording(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewSession:
    session = await _get_session_for_user(db, user, session_id)
    if session.status != SessionStatus.RECORDING.value:
        raise HTTPException(400, "仅 recording 可暂停")
    session.status = SessionStatus.PAUSED.value
    await db.commit()
    await db.refresh(session)
    return session


@router.patch("/sessions/{session_id}/active-ms", response_model=SessionOut)
async def update_active_ms(
    session_id: UUID,
    body: ActiveMsIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewSession:
    session = await _get_session_for_user(db, user, session_id)
    session.active_recording_ms = max(session.active_recording_ms, body.active_recording_ms)
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/sessions/{session_id}/finish", response_model=SessionOut)
async def finish_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewSession:
    """Client should call after local finishing hard-path completes."""
    session = await _get_session_for_user(db, user, session_id)
    if session.status not in {
        SessionStatus.RECORDING.value,
        SessionStatus.PAUSED.value,
        SessionStatus.FINISHING.value,
    }:
        raise HTTPException(400, f"当前状态不可结束: {session.status}")
    session.status = SessionStatus.FINISHING.value
    await db.commit()
    await db.refresh(session)
    return session


class FinishingCompleteIn(BaseModel):
    recovery_manifest: dict
    active_recording_ms: int | None = None


@router.post("/sessions/{session_id}/finishing-complete", response_model=SessionOut)
async def finishing_complete(
    session_id: UUID,
    body: FinishingCompleteIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewSession:
    session = await _get_session_for_user(db, user, session_id)
    if session.status != SessionStatus.FINISHING.value:
        raise HTTPException(400, "需要先进入 finishing")
    session.recovery_manifest = body.recovery_manifest
    if body.active_recording_ms is not None:
        session.active_recording_ms = body.active_recording_ms
    session.finished_at = utcnow()
    session.status = SessionStatus.PROCESSING.value
    await db.commit()
    # processing tasks may fail/retry; never block transition
    if session.cloud_processing_enabled:
        enqueue_session_processing.delay(str(session.id))
    await db.refresh(session)
    return session


@router.get("/projects/{project_id}/sessions", response_model=list[SessionOut])
async def list_sessions(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InterviewSession]:
    await get_owned_project(project_id, user, db)
    result = await db.execute(
        select(InterviewSession)
        .where(
            InterviewSession.project_id == project_id,
            InterviewSession.soft_deleted_at.is_(None),
        )
        .order_by(InterviewSession.created_at.desc())
    )
    return list(result.scalars().all())
