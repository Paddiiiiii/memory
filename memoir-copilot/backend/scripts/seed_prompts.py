"""Load prompt seeds into prompt_versions (idempotent)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import PromptVersion, new_id, utcnow

SEEDS = Path(__file__).resolve().parents[2] / "seeds" / "prompts"


async def main() -> None:
    async with SessionLocal() as db:
        for path in sorted(SEEDS.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            result = await db.execute(
                select(PromptVersion).where(
                    PromptVersion.prompt_name == data["prompt_name"],
                    PromptVersion.version == data["version"],
                )
            )
            if result.scalar_one_or_none():
                print("skip", path.name)
                continue
            if data.get("active"):
                # deactivate older actives for same name
                existing = await db.execute(
                    select(PromptVersion).where(
                        PromptVersion.prompt_name == data["prompt_name"],
                        PromptVersion.active.is_(True),
                    )
                )
                for row in existing.scalars():
                    row.active = False
            db.add(
                PromptVersion(
                    id=new_id(),
                    prompt_name=data["prompt_name"],
                    version=data["version"],
                    model_role=data["model_role"],
                    reasoning_effort=data.get("reasoning_effort", "low"),
                    schema_version=data.get("schema_version", "v1"),
                    prompt_text=data["prompt_text"],
                    active=bool(data.get("active", False)),
                    created_at=utcnow(),
                )
            )
            print("inserted", path.name)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
