from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_owned_project, list_user_projects
from app.core.database import get_db
from app.models import ConsentRecord, Project, Subject, User, utcnow
from app.schemas.api import ConsentIn, ProjectCreate, ProjectOut
from app.services.auth import service as auth_service
from app.services.state.merge import empty_interview_state

router = APIRouter(prefix="/projects", tags=["projects"])


def _subject_dict(s: Subject) -> dict:
    return {
        "id": str(s.id),
        "display_name": s.display_name,
        "preferred_address": s.preferred_address,
        "primary_language": s.primary_language,
        "dialect_hint": s.dialect_hint,
        "gender": s.gender,
        "birth_year": s.birth_year,
        "hometown": s.hometown,
        "occupation": s.occupation,
    }


@router.post("", response_model=ProjectOut)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    project = Project(owner_id=user.id, title=body.title)
    db.add(project)
    await db.flush()
    subject = Subject(
        project_id=project.id,
        display_name=body.subject.display_name,
        preferred_address=body.subject.preferred_address,
        primary_language=body.subject.primary_language,
        dialect_hint=body.subject.dialect_hint,
        gender=body.subject.gender,
        birth_year=body.subject.birth_year,
        birth_date=body.subject.birth_date,
        hometown=body.subject.hometown,
        occupation=body.subject.occupation,
        family_structure=body.subject.family_structure,
        bio=body.subject.bio,
        canonical_state=empty_interview_state("subject_canonical"),
    )
    db.add(subject)
    await auth_service.write_audit(
        db, actor_id=user.id, action="create_project", resource_type="project", resource_id=str(project.id)
    )
    await db.commit()
    await db.refresh(project)
    return ProjectOut(
        id=project.id,
        title=project.title,
        owner_id=project.owner_id,
        created_at=project.created_at,
        subject=_subject_dict(subject),
    )


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectOut]:
    projects = await list_user_projects(db, user)
    out: list[ProjectOut] = []
    for p in projects:
        result = await db.execute(select(Subject).where(Subject.project_id == p.id))
        subject = result.scalar_one_or_none()
        out.append(
            ProjectOut(
                id=p.id,
                title=p.title,
                owner_id=p.owner_id,
                created_at=p.created_at,
                subject=_subject_dict(subject) if subject else None,
            )
        )
    return out


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    project = await get_owned_project(project_id, user, db)
    await auth_service.write_audit(
        db, actor_id=user.id, action="open_project", resource_type="project", resource_id=str(project.id)
    )
    result = await db.execute(select(Subject).where(Subject.project_id == project.id))
    subject = result.scalar_one_or_none()
    await db.commit()
    return ProjectOut(
        id=project.id,
        title=project.title,
        owner_id=project.owner_id,
        created_at=project.created_at,
        subject=_subject_dict(subject) if subject else None,
    )


@router.post("/{project_id}/consents")
async def add_consent(
    project_id: UUID,
    body: ConsentIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_owned_project(project_id, user, db)
    result = await db.execute(select(Subject).where(Subject.project_id == project.id))
    subject = result.scalar_one_or_none()
    if subject is None:
        raise HTTPException(404, "Subject 不存在")
    rec = ConsentRecord(
        subject_id=subject.id,
        consent_type=body.consent_type,
        granted=body.granted,
        captured_by=user.id,
        method=body.method,
        version=body.version,
    )
    db.add(rec)
    await auth_service.write_audit(
        db,
        actor_id=user.id,
        action="modify_consent",
        resource_type="consent",
        resource_id=str(subject.id),
        meta={"consent_type": body.consent_type, "granted": body.granted},
    )
    await db.commit()
    return {"ok": True, "consent_type": body.consent_type, "granted": body.granted}


@router.delete("/{project_id}")
async def soft_delete_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_owned_project(project_id, user, db)
    project.soft_deleted_at = utcnow()
    await auth_service.write_audit(
        db, actor_id=user.id, action="delete", resource_type="project", resource_id=str(project.id)
    )
    await db.commit()
    return {"ok": True, "soft_delete_days": 7}
