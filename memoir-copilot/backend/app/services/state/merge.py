from __future__ import annotations

from copy import deepcopy
from typing import Any


REQUIRED_EVENT_SLOTS = ("cause", "process", "outcome", "emotion", "people", "place")


def empty_interview_state(scope: str) -> dict[str, Any]:
    return {
        "version": 1,
        "scope": scope,
        "timeline": [],
        "people": [],
        "places": [],
        "events": [],
        "relationships": [],
        "questions": [],
        "first_experiences": [],
        "open_loops": [],
        "gaps": [],
        "conflicts": [],
        "themes": [],
        "coverage": {},
    }


def _index_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(i["id"]): i for i in items if "id" in i}


def _merge_evidence(a: list[str], b: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in a + b:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _normalize_name(name: str) -> str:
    return "".join(name.strip().lower().split())


def validate_delta_evidence(delta: dict[str, Any], known_segment_ids: set[str]) -> dict[str, Any] | None:
    """Drop items with missing evidence; reject whole delta if >30% illegal."""
    items = delta.get("items") or []
    if not items:
        return delta
    kept: list[dict[str, Any]] = []
    illegal = 0
    for item in items:
        evidence = item.get("evidence") or item.get("payload", {}).get("evidence") or []
        if not evidence:
            illegal += 1
            continue
        if any(e not in known_segment_ids for e in evidence):
            illegal += 1
            continue
        kept.append(item)
    if len(items) > 0 and illegal / len(items) > 0.30:
        return None
    out = deepcopy(delta)
    out["items"] = kept
    return out


def apply_delta(state: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """Merge Engine: upsert entities, accumulate evidence, create conflicts on mutex claims."""
    new_state = deepcopy(state)
    people = _index_by_id(new_state.get("people") or [])
    places = _index_by_id(new_state.get("places") or [])
    events = _index_by_id(new_state.get("events") or [])
    questions = _index_by_id(new_state.get("questions") or [])
    open_loops = _index_by_id(new_state.get("open_loops") or [])
    conflicts = list(new_state.get("conflicts") or [])
    gaps = list(new_state.get("gaps") or [])

    for item in delta.get("items") or []:
        op = item.get("op")
        et = item.get("entity_type")
        payload = item.get("payload") or {}
        evidence = item.get("evidence") or payload.get("evidence") or []
        conf = float(item.get("confidence") or 0.5)

        if et == "person" and op in {"upsert", "add_claim"}:
            pid = str(payload.get("id") or "")
            if not pid:
                continue
            if pid in people:
                cur = people[pid]
                if payload.get("importance") is not None and conf >= 0.7:
                    cur["importance"] = max(float(cur.get("importance") or 0), float(payload["importance"]))
                cur["aliases"] = sorted(
                    set((cur.get("aliases") or []) + (payload.get("aliases") or []))
                )
                if payload.get("relationship") and not cur.get("relationship"):
                    cur["relationship"] = payload["relationship"]
                cur["evidence"] = _merge_evidence(cur.get("evidence") or [], evidence)
                # mention_count from unique evidence
                cur["mention_count"] = len(cur["evidence"])
            else:
                people[pid] = {
                    **payload,
                    "evidence": evidence,
                    "mention_count": len(set(evidence)),
                    "aliases": payload.get("aliases") or [],
                }

        elif et == "place" and op in {"upsert", "add_claim"}:
            plid = str(payload.get("id") or "")
            if not plid:
                continue
            if plid in places:
                cur = places[plid]
                cur["aliases"] = sorted(set((cur.get("aliases") or []) + (payload.get("aliases") or [])))
                cur["evidence"] = _merge_evidence(cur.get("evidence") or [], evidence)
            else:
                places[plid] = {**payload, "evidence": evidence, "aliases": payload.get("aliases") or []}

        elif et == "event" and op in {"upsert", "add_claim"}:
            eid = str(payload.get("id") or "")
            if not eid:
                continue
            if eid in events:
                cur = events[eid]
                if payload.get("importance") is not None and conf >= 0.7:
                    cur["importance"] = max(float(cur.get("importance") or 0), float(payload["importance"]))
                cur["evidence"] = _merge_evidence(cur.get("evidence") or [], evidence)
                # time conflict detection (year)
                old_year = _year_of(cur.get("time"))
                new_year = _year_of(payload.get("time"))
                if old_year and new_year and old_year != new_year:
                    conflicts.append(
                        {
                            "id": f"conflict_{eid}_{old_year}_{new_year}",
                            "type": "FACT_MUTEX",
                            "entity_type": "event",
                            "entity_id": eid,
                            "field": "time.year",
                            "claims": [
                                {"value": old_year, "evidence": cur.get("evidence") or [], "status": "open"},
                                {"value": new_year, "evidence": evidence, "status": "open"},
                            ],
                        }
                    )
                elif payload.get("time"):
                    cur["time"] = payload["time"]
                if payload.get("missing"):
                    cur["missing"] = sorted(set((cur.get("missing") or []) + payload["missing"]))
                if payload.get("completeness"):
                    cur["completeness"] = {**(cur.get("completeness") or {}), **payload["completeness"]}
            else:
                events[eid] = {**payload, "evidence": evidence}

        elif et == "question" and op in {"coverage", "upsert"}:
            qid = str(payload.get("id") or "")
            if not qid:
                continue
            if qid in questions:
                cur = questions[qid]
                if "covered_slots" in payload:
                    cur["covered_slots"] = sorted(
                        set((cur.get("covered_slots") or []) + payload["covered_slots"])
                    )
                if "missing_slots" in payload:
                    cur["missing_slots"] = payload["missing_slots"]
                req = set(cur.get("required_slots") or cur.get("missing_slots") or [])
                covered = set(cur.get("covered_slots") or [])
                if req:
                    cur["coverage"] = len(covered & req) / max(len(req), 1)
                elif "coverage" in payload:
                    cur["coverage"] = payload["coverage"]
                cur["evidence"] = _merge_evidence(cur.get("evidence") or [], evidence)
                if payload.get("status"):
                    cur["status"] = payload["status"]
            else:
                questions[qid] = payload

        elif et == "open_loop" and op in {"open_loop", "upsert"}:
            oid = str(payload.get("id") or "")
            if oid:
                open_loops[oid] = {**payload, "evidence": evidence or payload.get("evidence") or []}

        elif et == "gap" and op == "gap":
            gaps.append(payload)

        elif et == "conflict" and op == "conflict":
            conflicts.append(payload)

    new_state["people"] = list(people.values())
    new_state["places"] = list(places.values())
    new_state["events"] = list(events.values())
    new_state["questions"] = list(questions.values())
    new_state["open_loops"] = list(open_loops.values())
    new_state["conflicts"] = conflicts
    new_state["gaps"] = gaps
    new_state["timeline"] = _rebuild_timeline(new_state["events"])
    new_state["version"] = int(new_state.get("version") or 1) + 1
    return new_state


def _year_of(time_obj: Any) -> int | None:
    if not isinstance(time_obj, dict):
        return None
    for key in ("start", "earliest", "raw"):
        v = time_obj.get(key)
        if isinstance(v, str) and len(v) >= 4 and v[:4].isdigit():
            return int(v[:4])
    return None


def _rebuild_timeline(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(e: dict[str, Any]) -> tuple:
        t = e.get("time") or {}
        earliest = t.get("earliest") or t.get("start") or "9999"
        certainty_rank = {"certain": 0, "probable": 1, "approximate": 2, "uncertain": 3}.get(
            t.get("certainty") or "uncertain", 3
        )
        return (earliest, certainty_rank, e.get("id") or "")

    items = []
    for e in sorted(events, key=sort_key):
        t = e.get("time") or {}
        items.append(
            {
                "event_id": e.get("id"),
                "title": e.get("title"),
                "earliest": t.get("earliest") or t.get("start"),
                "latest": t.get("latest") or t.get("end"),
                "precision": t.get("precision"),
                "certainty": t.get("certainty"),
            }
        )
    return items


def merge_subject_canonical(canonical: dict[str, Any], session_final: dict[str, Any]) -> dict[str, Any]:
    """Merge session final into subject canonical without last-write-wins on mutex facts."""
    base = canonical if canonical else empty_interview_state("subject_canonical")
    base = deepcopy(base)
    base["scope"] = "subject_canonical"

    # Reuse apply_delta by treating session entities as upserts with evidence
    delta_items: list[dict[str, Any]] = []
    for person in session_final.get("people") or []:
        delta_items.append(
            {
                "op": "upsert",
                "entity_type": "person",
                "payload": person,
                "evidence": person.get("evidence") or ["session_final"],
                "confidence": 0.85,
            }
        )
    for place in session_final.get("places") or []:
        delta_items.append(
            {
                "op": "upsert",
                "entity_type": "place",
                "payload": place,
                "evidence": place.get("evidence") or ["session_final"],
                "confidence": 0.85,
            }
        )
    for event in session_final.get("events") or []:
        delta_items.append(
            {
                "op": "upsert",
                "entity_type": "event",
                "payload": event,
                "evidence": event.get("evidence") or ["session_final"],
                "confidence": 0.85,
            }
        )
    for ol in session_final.get("open_loops") or []:
        delta_items.append(
            {
                "op": "open_loop",
                "entity_type": "open_loop",
                "payload": ol,
                "evidence": ol.get("evidence") or ["session_final"],
                "confidence": 0.8,
            }
        )

    # For subject merge, allow synthetic evidence marker when coming from session final package
    known = set()
    for it in delta_items:
        for e in it.get("evidence") or []:
            known.add(e)

    delta = {"delta_id": "subject_merge", "analyzer": "FINAL_COVERAGE", "window": {"start_ms": 0, "end_ms": 0}, "items": delta_items}
    # Bypass segment check for subject merge package by temporarily trusting evidence lists
    merged = apply_delta(base, delta)
    # Carry unresolved conflicts forward
    existing_conflicts = list(base.get("conflicts") or [])
    merged["conflicts"] = existing_conflicts + [
        c for c in merged.get("conflicts") or [] if c not in existing_conflicts
    ]
    return merged


def resolve_conflict(
    state: dict[str, Any],
    conflict_id: str,
    *,
    chosen_value: Any,
    resolution_source: str,
) -> dict[str, Any]:
    new_state = deepcopy(state)
    conflicts = new_state.get("conflicts") or []
    for c in conflicts:
        if c.get("id") != conflict_id:
            continue
        for claim in c.get("claims") or []:
            if claim.get("value") == chosen_value:
                claim["status"] = "accepted"
            else:
                claim["status"] = "rejected"
        c["status"] = "resolved"
        c["resolved_value"] = chosen_value
        c["resolution_source"] = resolution_source
        # apply to entity if event year
        if c.get("entity_type") == "event" and c.get("field") == "time.year":
            for e in new_state.get("events") or []:
                if e.get("id") == c.get("entity_id"):
                    t = dict(e.get("time") or {})
                    year = int(chosen_value)
                    t["start"] = f"{year}-01-01"
                    t["end"] = f"{year}-12-31"
                    t["raw"] = str(chosen_value)
                    e["time"] = t
        break
    new_state["conflicts"] = conflicts
    new_state["version"] = int(new_state.get("version") or 1) + 1
    return new_state
