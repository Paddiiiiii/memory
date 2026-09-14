from __future__ import annotations

import base64
import hashlib
import hmac
import random
import time
from typing import Any
from urllib.parse import quote

from app.core.config import get_settings


class TencentASRConfigError(RuntimeError):
    """Raised when Tencent ASR credentials are incomplete."""


class TencentASRProvider:
    """Issues short-lived signed WSS URLs for desktop direct connect.

    SecretKey never leaves the server. Signature follows Tencent Cloud ASR V2
    realtime WebSocket auth (HMAC-SHA1 + Base64 + URL-encode).
    Docs: https://cloud.tencent.com/document/product/1093/48982
    """

    def realtime_ticket(
        self,
        *,
        session_id: str,
        voice_id: str,
        engine_model_type: str = "16k_zh",
    ) -> dict[str, Any]:
        settings = get_settings()
        app_id = (settings.tencent_asr_app_id or "").strip()
        secret_id = (settings.tencent_asr_secret_id or "").strip()
        secret_key = (settings.tencent_asr_secret_key or "").strip()
        if not app_id or not secret_id or not secret_key:
            raise TencentASRConfigError(
                "缺少腾讯云 ASR 配置：请设置 TENCENT_ASR_APP_ID / SECRET_ID / SECRET_KEY"
            )

        timestamp = int(time.time())
        expired = timestamp + 24 * 3600
        nonce = random.randint(100_000, 2_000_000_000)

        params: dict[str, str | int] = {
            "engine_model_type": engine_model_type,
            "expired": expired,
            "filter_dirty": 0,
            "filter_modal": 0,
            "filter_punc": 0,
            "needvad": 1,
            "nonce": nonce,
            "secretid": secret_id,
            "timestamp": timestamp,
            "voice_format": 1,  # PCM
            "voice_id": voice_id,
        }
        # Dictionary order; values left unescaped for alphanumeric-safe params (official style).
        query = "&".join(f"{k}={params[k]}" for k in sorted(params.keys()))
        sign_str = f"asr.cloud.tencent.com/asr/v2/{app_id}?{query}"
        digest = hmac.new(secret_key.encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha1).digest()
        signature = base64.b64encode(digest).decode("utf-8")
        signed_query = f"{query}&signature={quote(signature, safe='')}"
        wss_url = f"wss://asr.cloud.tencent.com/asr/v2/{app_id}?{signed_query}"

        return {
            "engine_model_type": engine_model_type,
            "app_id": app_id,
            "secret_id": secret_id,
            "expire_at": expired,
            "timestamp": timestamp,
            "nonce": nonce,
            "voice_id": voice_id,
            "session_id": session_id,
            "voice_format": 1,
            "sample_rate": 16000,
            "wss_url": wss_url,
            "note": "Desktop connects directly with wss_url; rotate before expire_at.",
        }
