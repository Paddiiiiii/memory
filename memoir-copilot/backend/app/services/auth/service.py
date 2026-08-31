from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import AuthSession, AuditLog, User, UserRole, utcnow


class AuthError(Exception):
    def __init__(self, message: str, code: str = "auth_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise AuthError("邮箱或密码错误", "invalid_credentials")
    return user


async def issue_tokens(
    db: AsyncSession,
    user: User,
    *,
    device_id: str | None = None,
    family_id: UUID | None = None,
    rotated_from_id: UUID | None = None,
) -> tuple[str, str]:
    settings = get_settings()
    refresh = generate_refresh_token()
    family = family_id or uuid7()
    session = AuthSession(
        user_id=user.id,
        refresh_token_family_id=family,
        refresh_token_hash=hash_token(refresh),
        device_id=device_id,
        expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
        rotated_from_id=rotated_from_id,
    )
    db.add(session)
    access = create_access_token(subject=str(user.id), token_version=user.token_version, role=user.role)
    await db.flush()
    return access, refresh


async def refresh_tokens(db: AsyncSession, refresh_token: str, device_id: str | None = None) -> tuple[str, str, User]:
    token_hash = hash_token(refresh_token)
    result = await db.execute(select(AuthSession).where(AuthSession.refresh_token_hash == token_hash))
    session = result.scalar_one_or_none()

    if session is None:
        # Possible reuse of already-rotated token: cannot know family without lookup by plaintext.
        # Client must re-login. (Reuse detection for known families handled when rotated_from matches.)
        raise AuthError("Refresh token 无效", "invalid_refresh")

    if session.revoked_at is not None:
        await revoke_family(db, session.refresh_token_family_id)
        raise AuthError("检测到 refresh token 复用，会话族已作废", "refresh_reuse")

    if session.expires_at < datetime.now(UTC):
        session.revoked_at = utcnow()
        raise AuthError("Refresh token 已过期", "refresh_expired")

    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthError("用户不可用", "user_inactive")

    # Rotate: revoke old, issue new in same family
    session.revoked_at = utcnow()
    access, new_refresh = await issue_tokens(
        db,
        user,
        device_id=device_id or session.device_id,
        family_id=session.refresh_token_family_id,
        rotated_from_id=session.id,
    )
    session.last_used_at = utcnow()
    return access, new_refresh, user


async def revoke_family(db: AsyncSession, family_id: UUID) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.refresh_token_family_id == family_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


async def revoke_all_user_sessions(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


async def bump_token_version(db: AsyncSession, user: User) -> None:
    user.token_version += 1
    await revoke_all_user_sessions(db, user.id)


async def ensure_bootstrap_admin(db: AsyncSession) -> User | None:
    settings = get_settings()
    email = settings.bootstrap_admin_email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return None  # idempotent: do not overwrite password
    user = User(
        email=email,
        password_hash=hash_password(settings.bootstrap_admin_password),
        role=UserRole.ADMIN.value,
        display_name="Admin",
        must_change_password=True,
    )
    db.add(user)
    await db.flush()
    return user


async def write_audit(
    db: AsyncSession,
    *,
    actor_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    meta: dict | None = None,
) -> None:
    # Never store transcript body in audit
    safe_meta = {k: v for k, v in (meta or {}).items() if k not in {"text", "transcript", "raw_text"}}
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            meta=safe_meta,
        )
    )
