from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_project
from app.core.database import get_db
from app.models import InterviewSession, MediaAsset, User, new_id, utcnow
from app.services.auth import service as auth_service

router = APIRouter(tags=["media-questions"])

QUESTION_BANK_PATH = (
    Path(__file__).resolve().parents[4] / "seeds" / "question_bank" / "question_bank_v1.json"
)
ALLOWED_MEDIA = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
}


def load_question_bank() -> dict[str, Any]:
    if not QUESTION_BANK_PATH.exists():
        return {"version": "missing", "topics": [], "questions": []}
    return json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))


class InjectQuestionsIn(BaseModel):
    replace: bool = False


@router.get("/question-bank")
async def get_question_bank(user: User = Depends(get_current_user)) -> dict[str, Any]:
    _ = user
    return load_question_bank()


@router.post("/sessions/{session_id}/questions/load-bank")
async def load_bank_into_session(
    session_id: UUID,
    body: InjectQuestionsIn | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(404, "Session 不存在")
    await get_owned_project(session.project_id, user, db)
    bank = load_question_bank()
    incoming = bank.get("questions") or []
    state = dict(session.live_state or {})
    existing = list(state.get("questions") or [])
    if body and body.replace:
        merged = incoming
    else:
        by_id = {q.get("id"): q for q in existing if q.get("id")}
        for q in incoming:
            if q.get("id") not in by_id:
                by_id[q["id"]] = q
        merged = list(by_id.values())
    state["questions"] = merged
    state["question_bank_version"] = bank.get("version")
    state["topics"] = bank.get("topics") or state.get("topics") or []
    session.live_state = state
    session.live_state_version = int(session.live_state_version or 0) + 1
    await db.commit()
    return {"ok": True, "count": len(merged), "version": session.live_state_version}


class MediaMetaIn(BaseModel):
    title: str = ""
    description: str | None = None
    approx_year: int | None = None
    session_id: UUID | None = None
    event_id: str | None = None
    person_id: str | None = None
    timestamp_ms: int | None = None


@router.post("/projects/{project_id}/media")
async def upload_media(
    project_id: UUID,
    file: UploadFile = File(...),
    title: str = Form(""),
    description: str | None = Form(None),
    approx_year: int | None = Form(None),
    session_id: UUID | None = Form(None),
    event_id: str | None = Form(None),
    person_id: str | None = Form(None),
    timestamp_ms: int | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_owned_project(project_id, user, db)
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MEDIA and not mime.startswith("image/"):
        # allow listed + generic image/*
        if mime not in ALLOWED_MEDIA:
            raise HTTPException(400, f"不支持的类型: {mime}")
    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(400, "文件过大（上限 50MB）")
    asset_id = new_id()
    ext = ALLOWED_MEDIA.get(mime, Path(file.filename or "bin").suffix or ".bin")
    # Local-dev storage under backend/.data/media (COS later)
    root = Path(__file__).resolve().parents[3] / ".data" / "media" / str(project.id)
    root.mkdir(parents=True, exist_ok=True)
    storage_key = f"{project.id}/{asset_id}{ext}"
    (root / f"{asset_id}{ext}").write_bytes(data)
    asset = MediaAsset(
        id=asset_id,
        project_id=project.id,
        session_id=session_id,
        type="artifact",
        title=title or (file.filename or "artifact"),
        description=description,
        approx_year=approx_year,
        event_id=event_id,
        person_id=person_id,
        timestamp_ms=timestamp_ms,
        storage_key=storage_key,
        mime_type=mime,
        created_at=utcnow(),
    )
    db.add(asset)
    await auth_service.write_audit(
        db,
        actor_id=user.id,
        action="upload_media",
        resource_type="media_asset",
        resource_id=str(asset_id),
        meta={"mime": mime, "bytes": len(data)},
    )
    await db.commit()
    return {"id": str(asset.id), "storage_key": storage_key, "type": "artifact"}


@router.get("/projects/{project_id}/media")
async def list_media(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await get_owned_project(project_id, user, db)
    result = await db.execute(select(MediaAsset).where(MediaAsset.project_id == project_id))
    return [
        {
            "id": str(a.id),
            "title": a.title,
            "description": a.description,
            "approx_year": a.approx_year,
            "session_id": str(a.session_id) if a.session_id else None,
            "event_id": a.event_id,
            "person_id": a.person_id,
            "timestamp_ms": a.timestamp_ms,
            "mime_type": a.mime_type,
            "type": a.type,
            "created_at": a.created_at.isoformat(),
        }
        for a in result.scalars().all()
    ]
