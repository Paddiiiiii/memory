from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.core.security import hash_password
from app.models import User, UserRole
from app.services.auth import service as auth_service

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateUserIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    display_name: str = ""
    role: str = UserRole.INTERVIEWER.value


class ResetPasswordIn(BaseModel):
    email: EmailStr
    new_password: str = Field(min_length=10)


@router.post("/users")
async def create_user(
    body: CreateUserIn,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(400, "用户已存在")
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role=body.role,
        display_name=body.display_name or body.email.split("@")[0],
        must_change_password=True,
    )
    db.add(user)
    await auth_service.write_audit(
        db, actor_id=admin.id, action="create_user", resource_type="user", resource_id=body.email
    )
    await db.commit()
    return {"ok": True, "email": user.email}


@router.post("/users/reset-password")
async def reset_password(
    body: ResetPasswordIn,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "用户不存在")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = True
    await auth_service.bump_token_version(db, user)
    await auth_service.write_audit(
        db, actor_id=admin.id, action="admin_reset_password", resource_type="user", resource_id=str(user.id)
    )
    await db.commit()
    return {"ok": True}


