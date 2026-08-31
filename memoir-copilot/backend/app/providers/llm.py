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
    """OpenAI Responses API adapter. Falls back to deterministic stub when no API key."""

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
            return self._stub(user)
        payload: dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "text": {"format": {"type": "json_object"}},
        }
        if reasoning_effort and reasoning_effort != "none":
            payload["reasoning"] = {"effort": reasoning_effort}
        async with httpx.AsyncClient(base_url=settings.openai_base_url, timeout=120.0) as client:
            resp = await client.post(
                "/responses",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            # Best-effort extract text
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
        """Offline-dev stub StateDelta — empty items so merge is no-op."""
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
