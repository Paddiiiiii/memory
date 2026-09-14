"""P1 smoke: login → project → session → ready → start → stub transcript → finish → export."""
from __future__ import annotations

import sys

import httpx

BASE = "http://127.0.0.1:8000"


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=30)
    h = c.get("/health")
    assert h.status_code == 200, h.text
    login = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "ChangeMeAdmin123!", "device_id": "p1"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = c.post(
        "/v1/projects",
        headers=headers,
        json={
            "title": "P1 Smoke",
            "subject": {"display_name": "测试老人", "preferred_address": "王大爷", "primary_language": "zh-CN"},
        },
    )
    assert proj.status_code == 200, proj.text
    pid = proj.json()["id"]
    c.post(f"/v1/projects/{pid}/consents", headers=headers, json={"consent_type": "RECORDING", "granted": True})
    c.post(
        f"/v1/projects/{pid}/consents",
        headers=headers,
        json={"consent_type": "CLOUD_AI_PROCESSING", "granted": False},
    )

    sess = c.post(f"/v1/projects/{pid}/sessions", headers=headers, json={"title": "P1"}).json()
    sid = sess["id"]
    ready = c.post(f"/v1/sessions/{sid}/ready", headers=headers).json()
    assert ready["status"] == "ready"
    assert ready["cloud_processing_enabled"] is False
    c.post(f"/v1/sessions/{sid}/start", headers=headers)
    c.post(
        f"/v1/sessions/{sid}/transcript/segments",
        headers={**headers, "Idempotency-Key": "p1-1"},
        json={
            "sequence_number": 1,
            "speaker_id": "speaker_0",
            "start_ms": 0,
            "end_ms": 2500,
            "raw_text": "我六九年去了武汉。",
            "confidence": 0.93,
        },
    )
    c.post(f"/v1/sessions/{sid}/finish", headers=headers)
    done = c.post(
        f"/v1/sessions/{sid}/finishing-complete",
        headers=headers,
        json={"recovery_manifest": {"chunks_finalized": True, "source": "p1_smoke"}, "active_recording_ms": 2500},
    ).json()
    assert done["status"] == "completed", done  # local-only finishes without cloud worker
    srt = c.get(f"/v1/sessions/{sid}/export/srt", headers=headers)
    js = c.get(f"/v1/sessions/{sid}/export/json", headers=headers)
    assert srt.status_code == 200 and "武汉" in srt.text
    assert js.status_code == 200
    print("P1 API smoke OK", sid)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:  # noqa: BLE001
        print("FAIL", e, file=sys.stderr)
        raise SystemExit(1)
