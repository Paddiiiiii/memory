from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from app.core.config import get_settings


class TencentASRProvider:
    """Issues short-lived credentials for desktop direct WSS; SecretKey never leaves server."""

    def realtime_ticket(self, *, session_id: str, voice_id: str) -> dict[str, Any]:
        settings = get_settings()
        expire = int(time.time()) + 600
        # Placeholder signature package — replace with official Tencent ASR V2 sign when keys present
        payload = f"{settings.tencent_asr_app_id}:{session_id}:{voice_id}:{expire}"
        sig = ""
        if settings.tencent_asr_secret_key:
            sig = hmac.new(
                settings.tencent_asr_secret_key.encode(),
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()
        return {
            "engine_model_type": "16k_zh_en_speaker_2.0",
            "app_id": settings.tencent_asr_app_id,
            "secret_id": settings.tencent_asr_secret_id,
            "expire_at": expire,
            "signature": sig,
            "voice_id": voice_id,
            "session_id": session_id,
            "wss_url": "wss://asr.cloud.tencent.com/asr/v2",
            "note": "Desktop connects directly; rotate ticket before expire_at.",
        }
