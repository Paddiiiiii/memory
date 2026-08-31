from app.services.state.merge import apply_delta, empty_interview_state, merge_subject_canonical, resolve_conflict
from app.services.state.scoring import score_question


def test_score_clamp():
    s = score_question(
        importance=1,
        coverage=0,
        current_topic_relevance=1,
        story_gap=1,
        life_significance=1,
        first_experience_bonus=1,
        recent_question_penalty=0,
        sensitive_topic_penalty=0,
        repeat_penalty=0,
    )
    assert 0 <= s <= 1
    assert s > 0.9


def test_merge_person_evidence_unique():
    state = empty_interview_state("session_live")
    delta1 = {
        "delta_id": "d1",
        "analyzer": "WINDOW_ANALYZER",
        "window": {"start_ms": 0, "end_ms": 600000},
        "items": [
            {
                "op": "upsert",
                "entity_type": "person",
                "payload": {"id": "p1", "name": "王师傅", "aliases": ["老"], "importance": 0.8},
                "evidence": ["seg_1"],
                "confidence": 0.9,
            }
        ],
    }
    state = apply_delta(state, delta1)
    delta2 = {
        "delta_id": "d2",
        "analyzer": "WINDOW_ANALYZER",
        "window": {"start_ms": 480000, "end_ms": 1200000},
        "items": [
            {
                "op": "upsert",
                "entity_type": "person",
                "payload": {"id": "p1", "name": "王师傅", "aliases": ["王建国"], "importance": 0.9},
                "evidence": ["seg_1", "seg_2"],
                "confidence": 0.95,
            }
        ],
    }
    state = apply_delta(state, delta2)
    person = state["people"][0]
    assert person["mention_count"] == 2
    assert set(person["aliases"]) == {"老", "王建国"}
    assert person["importance"] == 0.9


def test_event_year_conflict_and_resolve():
    state = empty_interview_state("session_live")
    state = apply_delta(
        state,
        {
            "delta_id": "a",
            "analyzer": "WINDOW_ANALYZER",
            "window": {"start_ms": 0, "end_ms": 1},
            "items": [
                {
                    "op": "upsert",
                    "entity_type": "event",
                    "payload": {
                        "id": "e1",
                        "title": "结婚",
                        "importance": 0.9,
                        "summary": "结婚",
                        "time": {"raw": "1972", "start": "1972-01-01", "precision": "year", "certainty": "probable"},
                    },
                    "evidence": ["s1"],
                    "confidence": 0.9,
                }
            ],
        },
    )
    state = apply_delta(
        state,
        {
            "delta_id": "b",
            "analyzer": "WINDOW_ANALYZER",
            "window": {"start_ms": 0, "end_ms": 1},
            "items": [
                {
                    "op": "upsert",
                    "entity_type": "event",
                    "payload": {
                        "id": "e1",
                        "title": "结婚",
                        "importance": 0.9,
                        "summary": "结婚",
                        "time": {"raw": "1973", "start": "1973-01-01", "precision": "year", "certainty": "probable"},
                    },
                    "evidence": ["s2"],
                    "confidence": 0.9,
                }
            ],
        },
    )
    assert any(c.get("field") == "time.year" for c in state["conflicts"])
    cid = state["conflicts"][0]["id"]
    state = resolve_conflict(state, cid, chosen_value=1973, resolution_source="结婚证照片")
    assert state["conflicts"][0]["status"] == "resolved"
    assert state["conflicts"][0]["claims"][0]["status"] in {"accepted", "rejected"}


def test_subject_merge_no_lww():
    s1 = empty_interview_state("session_final")
    s1["events"] = [
        {
            "id": "e1",
            "title": "结婚",
            "importance": 0.9,
            "summary": "结婚",
            "time": {"raw": "1972", "start": "1972-01-01", "precision": "year", "certainty": "probable"},
            "evidence": ["S1:seg_182"],
        }
    ]
    s2 = empty_interview_state("session_final")
    s2["events"] = [
        {
            "id": "e1",
            "title": "结婚",
            "importance": 0.9,
            "summary": "结婚",
            "time": {"raw": "1973", "start": "1973-01-01", "precision": "year", "certainty": "probable"},
            "evidence": ["S2:seg_091"],
        }
    ]
    canon = merge_subject_canonical({}, s1)
    canon = merge_subject_canonical(canon, s2)
    assert any(c.get("field") == "time.year" for c in canon.get("conflicts") or [])
