from __future__ import annotations

import os
from typing import Any

from superteam.core.contracts import LoopState
from .config import OpenRouterConfig


class OpenRouterProvider:
    def __init__(self, config: OpenRouterConfig | None = None):
        self.config = config or OpenRouterConfig()
        self.api_key = self.config.api_key or os.getenv("OPENROUTER_API_KEY")
        self.last_tokens: dict[str, int] = {}

    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "httpx is required for the OpenRouter provider. "
                "Install it with: uv sync --extra openrouter"
            ) from exc

        resp = httpx.post(
            f"{self.config.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        self._extract_usage(data)
        return data["choices"][0]["message"]["content"]

    def health(self) -> bool:
        return bool(self.api_key)

    def _extract_usage(self, data: dict[str, Any]) -> None:
        usage = data.get("usage", {})
        if usage:
            self.last_tokens = {
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }
