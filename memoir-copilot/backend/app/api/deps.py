from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import safe_decode
from app.models import Project, User

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    payload = safe_decode(creds.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 token")
    user = await db.get(User, UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不可用")
    if int(payload.get("tv", -1)) != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 已失效")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


async def get_owned_project(project_id: UUID, user: User, db: AsyncSession) -> Project:
    project = await db.get(Project, project_id)
    if project is None or project.soft_deleted_at is not None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if user.role != "admin" and project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="无权限")
    return project


async def list_user_projects(db: AsyncSession, user: User) -> list[Project]:
    if user.role == "admin":
        result = await db.execute(select(Project).where(Project.soft_deleted_at.is_(None)))
    else:
        result = await db.execute(
            select(Project).where(Project.owner_id == user.id, Project.soft_deleted_at.is_(None))
        )
    return list(result.scalars().all())
