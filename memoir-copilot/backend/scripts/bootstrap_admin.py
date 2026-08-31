from __future__ import annotations

import asyncio

from app.core.database import SessionLocal
from app.services.auth.service import ensure_bootstrap_admin


async def main() -> None:
    async with SessionLocal() as db:
        user = await ensure_bootstrap_admin(db)
        await db.commit()
        if user is None:
            print("Bootstrap admin already exists (idempotent, password not overwritten).")
        else:
            print(f"Created bootstrap admin: {user.email} (must_change_password=True)")


if __name__ == "__main__":
    asyncio.run(main())
