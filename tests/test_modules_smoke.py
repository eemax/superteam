from __future__ import annotations

import os
import shutil

import pytest

from superteam.modules.claude_code import ClaudeCodeModule
from superteam.modules.codex import CodexModule


pytestmark = pytest.mark.skipif(
    os.environ.get("SUPERTEAM_RUN_LIVE_SMOKE") != "1",
    reason="opt-in live smoke tests only",
)


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_claude_code_module_smoke():
    module = ClaudeCodeModule()
    assert module.health() is True


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
def test_codex_module_smoke():
    module = CodexModule()
    assert module.health() is True
