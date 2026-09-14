from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache
def seeds_root() -> Path:
    """Resolve seeds/ across local monorepo and Docker layouts."""
    env = os.environ.get("MEMOIR_SEEDS_DIR") or ""
    if env:
        p = Path(env)
        if p.exists():
            return p

    try:
        from app.core.config import get_settings

        configured = (get_settings().memoir_seeds_dir or "").strip()
        if configured:
            p = Path(configured)
            if p.exists():
                return p
    except Exception:  # noqa: BLE001
        pass

    here = Path(__file__).resolve()
    # media.py lives at backend/app/api/v1 → parents[4] == memoir-copilot
    candidates = [
        here.parents[4] / "seeds",
        here.parents[3] / "seeds",  # if packaged flatter
        Path("/app/seeds"),
        Path("/seeds"),
        Path.cwd() / "seeds",
        Path.cwd().parent / "seeds",
    ]
    for c in candidates:
        if (c / "question_bank" / "question_bank_v1.json").exists():
            return c
    return candidates[0]


def question_bank_path() -> Path:
    return seeds_root() / "question_bank" / "question_bank_v1.json"


def prompts_dir() -> Path:
    return seeds_root() / "prompts"
