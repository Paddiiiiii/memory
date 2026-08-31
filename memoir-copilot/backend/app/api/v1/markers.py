from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB

from app.api.deps import get_current_user, get_owned_project
from app.core.database import Base, get_db
from app.models import InterviewSession, User, new_id, utcnow
from datetime import datetime

router = APIRouter(tags=["markers-notes"])


class SessionMarker(Base):
    __tablename__ = "session_markers"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=new_id)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    marker_type: Mapped[str] = mapped_column(String(32))
    timestamp_ms: Mapped[int] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    segment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionNote(Base):
    __tablename__ = "session_notes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=new_id)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    timestamp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64), default="SOURCE_INTERVIEWER_OBSERVATION")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MarkerIn(BaseModel):
    marker_type: str = Field(description="KEY_MOMENT|FOLLOW_UP|EMOTION|FACT_CHECK|QUOTE|MEDIA")
    timestamp_ms: int
    text: str | None = None
    segment_id: str | None = None


class NoteIn(BaseModel):
    text: str
    timestamp_ms: int | None = None
    general: bool = False


ALLOWED_MARKERS = {"KEY_MOMENT", "FOLLOW_UP", "EMOTION", "FACT_CHECK", "QUOTE", "MEDIA"}


async def _session(db: AsyncSession, user: User, session_id: UUID) -> InterviewSession:
    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(404, "Session 不存在")
    await get_owned_project(session.project_id, user, db)
    return session


@router.post("/sessions/{session_id}/markers")
async def add_marker(
    session_id: UUID,
    body: MarkerIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.marker_type not in ALLOWED_MARKERS:
        raise HTTPException(400, f"marker_type 必须是 {sorted(ALLOWED_MARKERS)}")
    await _session(db, user, session_id)
    row = SessionMarker(
        session_id=session_id,
        marker_type=body.marker_type,
        timestamp_ms=body.timestamp_ms,
        text=body.text,
        segment_id=body.segment_id,
    )
    db.add(row)
    await db.commit()
    return {"id": str(row.id), "marker_type": row.marker_type, "timestamp_ms": row.timestamp_ms}


@router.get("/sessions/{session_id}/markers")
async def list_markers(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _session(db, user, session_id)
    result = await db.execute(
        select(SessionMarker).where(SessionMarker.session_id == session_id).order_by(SessionMarker.timestamp_ms)
    )
    return [
        {
            "id": str(m.id),
            "marker_type": m.marker_type,
            "timestamp_ms": m.timestamp_ms,
            "text": m.text,
            "segment_id": m.segment_id,
        }
        for m in result.scalars().all()
    ]


@router.post("/sessions/{session_id}/notes")
async def add_note(
    session_id: UUID,
    body: NoteIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _session(db, user, session_id)
    row = SessionNote(
        session_id=session_id,
        text=body.text,
        timestamp_ms=None if body.general else body.timestamp_ms,
    )
    db.add(row)
    await db.commit()
    return {"id": str(row.id), "timestamp_ms": row.timestamp_ms}


@router.get("/sessions/{session_id}/notes")
async def list_notes(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _session(db, user, session_id)
    result = await db.execute(select(SessionNote).where(SessionNote.session_id == session_id))
    return [
        {
            "id": str(n.id),
            "text": n.text,
            "timestamp_ms": n.timestamp_ms,
            "source": n.source,
        }
        for n in result.scalars().all()
    ]
