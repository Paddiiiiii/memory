from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_project
from app.core.database import get_db
from app.models import InterviewSession, Subject, User
from app.services.state.merge import merge_subject_canonical, resolve_conflict
from app.services.state.scoring import rank_suggestions
from app.workers.tasks import enqueue_final_review, enqueue_global_analysis, enqueue_window_analysis

router = APIRouter(tags=["state-analysis"])


async def _session(db: AsyncSession, user: User, session_id: UUID) -> InterviewSession:
    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(404, "Session 不存在")
    await get_owned_project(session.project_id, user, db)
    return session


@router.get("/sessions/{session_id}/state")
async def get_state(
    session_id: UUID,
    which: str = "live",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, user, session_id)
    if which == "final":
        return {"version": session.final_state_version, "state": session.final_state}
    return {"version": session.live_state_version, "state": session.live_state}


@router.get("/sessions/{session_id}/suggestions")
async def suggestions(
    session_id: UUID,
    current_topic: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    session = await _session(db, user, session_id)
    state = session.live_state or {}
    questions = state.get("questions") or []
    return rank_suggestions(
        questions,
        current_topic=current_topic or state.get("coverage", {}).get("current_topic"),
        parent_map={},
        sensitive_ids=set(),
        subject_opened_sensitive=set(),
        top_n=5,
    )


class QuestionActionBody(BaseModel):
    question_id: str
    action: str


@router.post("/sessions/{session_id}/questions/actions")
async def question_action(
    session_id: UUID,
    body: QuestionActionBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, user, session_id)
    state = dict(session.live_state or {})
    questions = list(state.get("questions") or [])
    found = False
    for q in questions:
        if q.get("id") == body.question_id:
            found = True
            if body.action == "pin":
                q["pinned"] = True
            elif body.action == "asked":
                q["status"] = "asked"
            elif body.action == "ignore":
                q["session_ignored"] = True
            elif body.action == "later":
                q["later"] = True
            break
    if not found:
        raise HTTPException(404, "问题不存在")
    state["questions"] = questions
    session.live_state = state
    session.live_state_version = int(session.live_state_version or 0) + 1
    await db.commit()
    return {"ok": True, "version": session.live_state_version}


@router.post("/sessions/{session_id}/analysis/window")
async def trigger_window(
    session_id: UUID,
    end_ms: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, user, session_id)
    if not session.cloud_processing_enabled:
        raise HTTPException(400, "仅本地模式，未启用云端分析")
    enqueue_window_analysis.delay(str(session.id), end_ms)
    return {"queued": True}


@router.post("/sessions/{session_id}/analysis/global")
async def trigger_global(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, user, session_id)
    if not session.cloud_processing_enabled:
        raise HTTPException(400, "仅本地模式")
    enqueue_global_analysis.delay(str(session.id))
    return {"queued": True}


@router.post("/sessions/{session_id}/analysis/final")
async def trigger_final(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """准备收尾 — 可多次；worker 侧做 5min / 3min transcript 缓存."""
    session = await _session(db, user, session_id)
    if not session.cloud_processing_enabled:
        raise HTTPException(400, "仅本地模式")
    enqueue_final_review.delay(str(session.id))
    return {"queued": True}


class ResolveConflictIn(BaseModel):
    conflict_id: str
    chosen_value: str | int
    resolution_source: str
    scope: str = "subject"  # subject | session_final | session_live


@router.post("/projects/{project_id}/canonical/resolve-conflict")
async def resolve_subject_conflict(
    project_id: UUID,
    body: ResolveConflictIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_owned_project(project_id, user, db)
    from sqlalchemy import select
    from app.models import Subject

    result = await db.execute(select(Subject).where(Subject.project_id == project.id))
    subject = result.scalar_one_or_none()
    if subject is None:
        raise HTTPException(404, "Subject 不存在")
    subject.canonical_state = resolve_conflict(
        subject.canonical_state or {},
        body.conflict_id,
        chosen_value=body.chosen_value,
        resolution_source=body.resolution_source,
    )
    await db.commit()
    return {"ok": True, "canonical_version": (subject.canonical_state or {}).get("version")}


@router.post("/sessions/{session_id}/merge-to-subject")
async def merge_to_subject(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await _session(db, user, session_id)
    subject = await db.get(Subject, session.subject_id)
    if subject is None:
        raise HTTPException(404, "Subject 不存在")
    subject.canonical_state = merge_subject_canonical(
        subject.canonical_state or {}, session.final_state or {}
    )
    await db.commit()
    return {"ok": True, "version": (subject.canonical_state or {}).get("version")}
