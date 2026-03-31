from __future__ import annotations

from pathlib import Path
import subprocess

from superteam.modules.claude_code import ClaudeCodeConfig, ClaudeCodeModule
from superteam.modules.codex import CodexConfig, CodexModule


def test_codex_module_builds_command_and_reads_last_message(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_run(cmd, input, capture_output, cwd, timeout, env, check):
        captured["cmd"] = cmd
        captured["input"] = input.decode("utf-8")
        captured["cwd"] = cwd
        output_path = Path(cmd[cmd.index("-o") + 1])
        output_path.write_text("final answer", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr("superteam.modules.codex.runner.subprocess.run", fake_run)

    module = CodexModule(
        CodexConfig(
            model="gpt-5-codex",
            profile="default",
            skip_git_repo_check=True,
            extra_args=["--ephemeral"],
        )
    )
    output = module.run("auditor", "Be strict.", "Review this output.", cwd=str(tmp_path))

    assert output == "final answer"
    assert captured["cwd"] == str(tmp_path)
    assert captured["cmd"][:2] == ["codex", "exec"]
    assert "--model" in captured["cmd"]
    assert "--profile" in captured["cmd"]
    assert "--skip-git-repo-check" in captured["cmd"]
    assert "--ephemeral" in captured["cmd"]
    assert "## System Instructions" in captured["input"]
    assert "Review this output." in captured["input"]


def test_codex_module_raises_on_nonzero_exit(monkeypatch, tmp_path):
    def fake_run(cmd, input, capture_output, cwd, timeout, env, check):
        return subprocess.CompletedProcess(cmd, 1, b"", b"boom")

    monkeypatch.setattr("superteam.modules.codex.runner.subprocess.run", fake_run)

    module = CodexModule(CodexConfig())
    try:
        module.run("builder", "sys", "prompt", cwd=str(tmp_path))
    except RuntimeError as exc:
        assert "codex exec exited with code 1" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_codex_module_health(monkeypatch):
    monkeypatch.setattr("superteam.modules.codex.runner.shutil.which", lambda _: "/usr/bin/codex")
    assert CodexModule().health() is True


def test_claude_code_module_builds_command(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_run(cmd, input, capture_output, cwd, timeout, env, check):
        captured["cmd"] = cmd
        captured["input"] = input.decode("utf-8")
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(cmd, 0, b'{"result":"done"}', b"")

    monkeypatch.setattr("superteam.modules.claude_code.runner.subprocess.run", fake_run)

    module = ClaudeCodeModule(
        ClaudeCodeConfig(
            model="claude-opus-4-1",
            timeout=42,
            allowed_tools=["Bash", "Edit"],
            permission_mode="auto",
            bare=True,
        )
    )
    output = module.run("builder", "System prompt", "Task prompt", cwd=str(tmp_path))

    assert output == "done"
    assert captured["cwd"] == str(tmp_path)
    assert captured["cmd"][:2] == ["claude", "-p"]
    assert "--system-prompt" in captured["cmd"]
    assert "--allowedTools" in captured["cmd"]
    assert "--permission-mode" in captured["cmd"]
    assert "--bare" in captured["cmd"]
    assert captured["input"] == "Task prompt"


def test_claude_code_module_health(monkeypatch):
    monkeypatch.setattr("superteam.modules.claude_code.runner.shutil.which", lambda _: "/usr/bin/claude")
    assert ClaudeCodeModule().health() is True
