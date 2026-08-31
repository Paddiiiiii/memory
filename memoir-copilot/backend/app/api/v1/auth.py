from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.api import ChangePasswordRequest, LoginRequest, RefreshRequest, TokenPair, UserOut
from app.services.auth import service as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    try:
        user = await auth_service.authenticate(db, body.email, body.password)
        access, refresh = await auth_service.issue_tokens(db, user, device_id=body.device_id)
        await auth_service.write_audit(
            db, actor_id=user.id, action="login", resource_type="user", resource_id=str(user.id)
        )
        await db.commit()
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            must_change_password=user.must_change_password,
        )
    except auth_service.AuthError as e:
        raise HTTPException(status_code=401, detail=e.message) from e


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    try:
        access, refresh_token, user = await auth_service.refresh_tokens(
            db, body.refresh_token, device_id=body.device_id
        )
        await db.commit()
        return TokenPair(
            access_token=access,
            refresh_token=refresh_token,
            must_change_password=user.must_change_password,
        )
    except auth_service.AuthError as e:
        await db.commit()
        raise HTTPException(status_code=401, detail=e.message) from e


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码错误")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    await auth_service.bump_token_version(db, user)
    await auth_service.write_audit(
        db, actor_id=user.id, action="change_password", resource_type="user", resource_id=str(user.id)
    )
    await db.commit()
    return {"ok": True}
