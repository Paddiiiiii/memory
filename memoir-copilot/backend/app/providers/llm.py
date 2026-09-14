from __future__ import annotations

import json
import logging
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    async def structured(
        self,
        *,
        model: str,
        system: str,
        user: Any,
        reasoning_effort: str | None = None,
    ) -> Any: ...


class OpenAIResponsesProvider:
    """OpenAI-compatible adapter.

    Prefers Chat Completions JSON mode (widely supported). Falls back to Responses API.
    When no API key: returns empty StateDelta stub (dev-only; logged as warning).
    """

    async def structured(
        self,
        *,
        model: str,
        system: str,
        user: Any,
        reasoning_effort: str | None = None,
    ) -> Any:
        settings = get_settings()
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY 未配置，LLM 返回 stub（不会写入真实分析）")
            return self._stub(user)

        user_text = json.dumps(user, ensure_ascii=False)
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        async with httpx.AsyncClient(base_url=settings.openai_base_url, timeout=120.0) as client:
            # 1) Chat Completions — works with OpenAI + most compatible gateways
            chat_payload: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            }
            chat = await client.post("/chat/completions", headers=headers, json=chat_payload)
            if chat.status_code < 400:
                data = chat.json()
                text = (
                    ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                ).strip()
                if text:
                    return json.loads(text)

            # 2) Responses API fallback (newer OpenAI surface)
            resp_payload: dict[str, Any] = {
                "model": model,
                "input": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
                "text": {"format": {"type": "json_object"}},
            }
            if reasoning_effort and reasoning_effort != "none":
                resp_payload["reasoning"] = {"effort": reasoning_effort}
            resp = await client.post("/responses", headers=headers, json=resp_payload)
            resp.raise_for_status()
            data = resp.json()
            text = data.get("output_text")
            if not text:
                for item in data.get("output") or []:
                    for c in item.get("content") or []:
                        if c.get("type") in {"output_text", "text"} and c.get("text"):
                            text = c["text"]
                            break
            if not text:
                return data
            return json.loads(text)

    def _stub(self, user: Any) -> dict[str, Any]:
        window = {}
        if isinstance(user, dict):
            window = user.get("window") or {"start_ms": 0, "end_ms": 0}
        return {
            "delta_id": "stub",
            "analyzer": "WINDOW_ANALYZER",
            "window": window,
            "items": [],
            "questions": [],
            "suggestions": [],
        }


_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = OpenAIResponsesProvider()
    return _provider
