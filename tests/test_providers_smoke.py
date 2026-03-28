from __future__ import annotations

import importlib.util
import os
import shutil

import pytest

from superteam.core.contracts import LoopState
from superteam.providers.claude_api import ClaudeAPIConfig, ClaudeAPIProvider
from superteam.providers.claude_code import ClaudeCodeProvider


pytestmark = pytest.mark.skipif(
    os.environ.get("SUPERTEAM_RUN_LIVE_SMOKE") != "1",
    reason="opt-in live smoke tests only",
)


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_claude_code_provider_smoke():
    provider = ClaudeCodeProvider()
    assert provider.health() is True


@pytest.mark.skipif(importlib.util.find_spec("anthropic") is None, reason="anthropic package not installed")
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
def test_claude_api_provider_smoke():
    provider = ClaudeAPIProvider(ClaudeAPIConfig(max_tokens=32, temperature=0.0))
    output = provider.complete(
        "You are terse.",
        "Respond with the single word ok.",
        LoopState(session_id="st-smoke", goal="goal", plan="plan"),
    )
    assert output.strip()
