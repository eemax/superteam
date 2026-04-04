from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import shutil
import subprocess

from superteam.core.contracts import LoopState

from .config import CodexConfig


class CodexModule:
    def __init__(self, config: CodexConfig = CodexConfig()):
        self.config = config

    def run(
        self,
        role: str,
        system: str,
        prompt: str,
        state: LoopState | None = None,
        cwd: str | None = None,
    ) -> str:
        working_dir = self._resolve_working_dir(cwd)
        full_prompt = self._build_prompt(role, system, prompt)

        with TemporaryDirectory(prefix="superteam-codex-") as temp_dir:
            output_path = Path(temp_dir) / "last-message.txt"
            cmd = ["codex", "exec", "--color", "never", "-o", str(output_path)]
            if working_dir:
                cmd.extend(["-C", working_dir])
            if self.config.model:
                cmd.extend(["--model", self.config.model])
            if self.config.profile:
                cmd.extend(["--profile", self.config.profile])
            if self.config.skip_git_repo_check:
                cmd.append("--skip-git-repo-check")
            if self.config.extra_args:
                cmd.extend(self.config.extra_args)

            # Intentionally forward full environment; child process needs API keys, PATH, etc.
            env = os.environ.copy()
            try:
                result = subprocess.run(
                    cmd,
                    input=full_prompt.encode("utf-8"),
                    capture_output=True,
                    cwd=working_dir,
                    timeout=self.config.timeout,
                    env=env,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError(f"codex exec timed out after {self.config.timeout}s") from exc
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "codex binary not found. Is Codex CLI installed and on PATH?"
                ) from exc

            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()
                stdout = result.stdout.decode("utf-8", errors="replace").strip()
                details = stderr or stdout or "no output"
                raise RuntimeError(f"codex exec exited with code {result.returncode}.\noutput: {details}")

            if output_path.exists():
                output = output_path.read_text(encoding="utf-8").strip()
                if output:
                    return output
            return result.stdout.decode("utf-8", errors="replace")

    def health(self) -> bool:
        return shutil.which("codex") is not None

    def capabilities(self) -> set[str]:
        return {"builder", "auditor"}

    def _resolve_working_dir(self, cwd: str | None) -> str | None:
        return self.config.working_dir or cwd

    def _build_prompt(self, role: str, system: str, prompt: str) -> str:
        return (
            f"## Role\n{role}\n\n"
            f"## System Instructions\n{system.strip()}\n\n"
            f"## Task\n{prompt.strip()}\n"
        )
