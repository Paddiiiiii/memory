from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_project
from app.core.database import get_db
from app.models import InterviewSession, User
from app.providers.tencent_asr import TencentASRProvider

router = APIRouter(prefix="/asr", tags=["asr"])


class TicketIn(BaseModel):
    session_id: UUID
    voice_id: str


@router.post("/realtime-ticket")
async def realtime_ticket(
    body: TicketIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await db.get(InterviewSession, body.session_id)
    if session is None:
        raise HTTPException(404, "Session 不存在")
    await get_owned_project(session.project_id, user, db)
    if not session.cloud_processing_enabled:
        raise HTTPException(400, "仅本地录音模式，未启用云端 ASR")
    return TencentASRProvider().realtime_ticket(
        session_id=str(session.id), voice_id=body.voice_id
    )
