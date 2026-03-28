from __future__ import annotations

import logging
from pathlib import Path
import json
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

from superteam.core.contracts import LoopState
from superteam.core.session import sessions_dir

from .config import ClaudeCodeConfig


class ClaudeCodeProvider:
    def __init__(self, config: ClaudeCodeConfig = ClaudeCodeConfig()):
        self.config = config
        self.last_tokens: dict[str, int] = {}

    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        cwd = self._resolve_working_dir(state)
        cmd = [
            "claude",
            "-p",
            "--model",
            self.config.model,
            "--output-format",
            "json",
            "--system-prompt",
            system,
        ]
        # Current Claude Code builds do not expose a max-turns flag in print mode.
        if self.config.max_turns is not None:
            logger.warning(
                "max_turns=%d is set but Claude Code print mode does not support --max-turns; ignoring",
                self.config.max_turns,
            )
        if self.config.bare:
            cmd.append("--bare")
        if self.config.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.config.allowed_tools)])
        if self.config.permission_mode:
            cmd.extend(["--permission-mode", self.config.permission_mode])

        env = {**os.environ, **(self.config.env or {})}
        try:
            result = subprocess.run(
                cmd,
                input=prompt.encode("utf-8"),
                capture_output=True,
                cwd=cwd,
                timeout=self.config.timeout,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"claude -p timed out after {self.config.timeout}s") from exc

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"claude -p exited with code {result.returncode}.\nstderr: {stderr}"
            )

        return self._parse_output(result.stdout.decode("utf-8", errors="replace"))

    def health(self) -> bool:
        return shutil.which("claude") is not None

    def _resolve_working_dir(self, state: LoopState | None) -> str | None:
        if self.config.working_dir:
            return self.config.working_dir
        if state is None:
            return None
        workspace = sessions_dir() / state.session_id / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        return str(workspace)

    def _parse_output(self, raw: str) -> str:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self.last_tokens = {}
            return raw

        self.last_tokens = self._parse_usage(data)
        if isinstance(data, dict):
            if isinstance(data.get("result"), str):
                return data["result"]
            if isinstance(data.get("text"), str):
                return data["text"]
            if isinstance(data.get("content"), list):
                chunks = []
                for item in data["content"]:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        chunks.append(item["text"])
                if chunks:
                    return "".join(chunks)
        return raw

    def _parse_usage(self, data: dict) -> dict[str, int]:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return {}

        parsed: dict[str, int] = {}
        for target, keys in {
            "input": ("input_tokens", "inputTokens"),
            "output": ("output_tokens", "outputTokens"),
        }.items():
            for key in keys:
                value = usage.get(key)
                if isinstance(value, int):
                    parsed[target] = value
                    break
        if "input" in parsed or "output" in parsed:
            parsed["total"] = parsed.get("input", 0) + parsed.get("output", 0)
        return parsed
