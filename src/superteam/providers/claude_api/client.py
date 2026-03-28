from __future__ import annotations

from superteam.core.contracts import LoopState

from .config import ClaudeAPIConfig


class ClaudeAPIProvider:
    def __init__(self, config: ClaudeAPIConfig = ClaudeAPIConfig()):
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic is required for ClaudeAPIProvider. Install with the 'claude' extra."
            ) from exc

        self.config = config
        self.client = Anthropic(api_key=config.api_key)
        self.last_tokens: dict[str, int] = {}

    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens = getattr(usage, "input_tokens", None)
            output_tokens = getattr(usage, "output_tokens", None)
            self.last_tokens = {
                key: value
                for key, value in {
                    "input": input_tokens,
                    "output": output_tokens,
                    "total": (input_tokens or 0) + (output_tokens or 0),
                }.items()
                if isinstance(value, int)
            }
        else:
            self.last_tokens = {}

        text_parts: list[str] = []
        for block in getattr(response, "content", []):
            text = getattr(block, "text", None)
            if text:
                text_parts.append(text)
        return "".join(text_parts)

    def health(self) -> bool:
        return bool(getattr(self.client, "api_key", None))
