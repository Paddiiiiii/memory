from __future__ import annotations

from typing import Any


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_question(
    *,
    importance: float,
    coverage: float,
    current_topic_relevance: float,
    story_gap: float,
    life_significance: float,
    first_experience_bonus: float,
    recent_question_penalty: float,
    sensitive_topic_penalty: float,
    repeat_penalty: float,
) -> float:
    raw = (
        0.25 * importance
        + 0.25 * (1.0 - coverage)
        + 0.20 * current_topic_relevance
        + 0.15 * story_gap
        + 0.10 * life_significance
        + 0.05 * first_experience_bonus
        - 0.30 * recent_question_penalty
        - 0.25 * sensitive_topic_penalty
        - 0.20 * repeat_penalty
    )
    return clamp01(raw)


def recent_penalty_from_minutes(minutes_since_asked: float | None) -> float:
    if minutes_since_asked is None:
        return 0.0
    if minutes_since_asked < 5:
        return 1.0
    if minutes_since_asked < 10:
        return 0.6
    if minutes_since_asked < 20:
        return 0.3
    return 0.0


def topic_relevance(q_topic: str, current_topic: str | None, parent_map: dict[str, str | None]) -> float:
    if not current_topic or current_topic == "mixed":
        return 0.4
    if q_topic == current_topic:
        return 1.0
    if parent_map.get(q_topic) == current_topic or parent_map.get(current_topic) == q_topic:
        return 0.7
    # sibling under same parent
    if parent_map.get(q_topic) and parent_map.get(q_topic) == parent_map.get(current_topic):
        return 0.4
    return 0.0


def rank_suggestions(
    questions: list[dict[str, Any]],
    *,
    current_topic: str | None,
    parent_map: dict[str, str | None],
    sensitive_ids: set[str],
    subject_opened_sensitive: set[str],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for q in questions:
        if q.get("session_ignored"):
            continue
        if q.get("status") == "asked" and q.get("coverage", 0) >= 0.95:
            continue
        sens = 0.0
        tags = set(q.get("tags") or [])
        if any(t in sensitive_ids for t in tags | {q.get("primary_topic")}):
            sens = 1.0
            if tags & subject_opened_sensitive:
                sens = 0.3
        s = score_question(
            importance=float(q.get("importance") or 0.5),
            coverage=float(q.get("coverage") or 0.0),
            current_topic_relevance=topic_relevance(q.get("primary_topic") or "", current_topic, parent_map),
            story_gap=float(q.get("story_gap") or 0.0),
            life_significance=float(q.get("life_significance") or 0.5),
            first_experience_bonus=1.0 if q.get("first_experience_bonus") else 0.0,
            recent_question_penalty=recent_penalty_from_minutes(q.get("minutes_since_asked")),
            sensitive_topic_penalty=sens,
            repeat_penalty=float(q.get("repeat_penalty") or 0.0),
        )
        if q.get("pinned"):
            s = clamp01(s + 0.5)
        item = {**q, "score": s}
        scored.append(item)
    scored.sort(key=lambda x: (-(1 if x.get("pinned") else 0), -x["score"], x.get("id") or ""))
    return scored[:top_n]
