from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass
class ResolvedModel:
    role: str
    provider: str
    model_id: str
    reasoning_effort: str
    model_snapshot: str | None = None


# Env default → (future) Prompt Registry override
ROLE_MAP = {
    "WINDOW_ANALYZER": ("window_analyzer_model", "low"),
    "GLOBAL_ANALYZER": ("global_analyzer_model", "medium"),
    "FINAL_REVIEW": ("final_review_model", "high"),
    "TRANSCRIPT_CLEANER": ("transcript_cleaner_model", "low"),
    "THIRD_OPINION_ASR": ("third_opinion_asr_model", "none"),
    "WATCH_ASR": ("watch_asr_model", "none"),
}


def resolve_model(role: str) -> ResolvedModel:
    settings = get_settings()
    if role not in ROLE_MAP:
        raise KeyError(f"Unknown model role: {role}")
    attr, effort = ROLE_MAP[role]
    model_id = getattr(settings, attr)
    provider = "openai"
    return ResolvedModel(role=role, provider=provider, model_id=model_id, reasoning_effort=effort)
