from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

from superteam.core.contracts import LoopState

from .config import ClaudeCodeConfig


class ClaudeCodeModule:
    def __init__(self, config: ClaudeCodeConfig = ClaudeCodeConfig()):
        self.config = config

    def run(
        self,
        role: str,
        system: str,
        prompt: str,
        state: LoopState | None = None,
        cwd: str | None = None,
    ) -> str:
        cmd = [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--system-prompt",
            system,
        ]
        if self.config.model:
            cmd.extend(["--model", self.config.model])
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

        # Intentionally forward full environment; child process needs API keys, PATH, etc.
        env = {**os.environ, **(self.config.env or {})}
        try:
            result = subprocess.run(
                cmd,
                input=prompt.encode("utf-8"),
                capture_output=True,
                cwd=self._resolve_working_dir(cwd),
                timeout=self.config.timeout,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"claude -p timed out after {self.config.timeout}s") from exc
        except FileNotFoundError as exc:
            raise RuntimeError(
                "claude binary not found. Is Claude Code CLI installed and on PATH?"
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"claude -p exited with code {result.returncode}.\nstderr: {stderr}"
            )

        return self._parse_output(result.stdout.decode("utf-8", errors="replace"))

    def health(self) -> bool:
        return shutil.which("claude") is not None

    def capabilities(self) -> set[str]:
        return {"builder", "auditor"}

    def _resolve_working_dir(self, cwd: str | None) -> str | None:
        return self.config.working_dir or cwd

    def _parse_output(self, raw: str) -> str:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw

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
