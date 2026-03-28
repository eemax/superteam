from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_superteam_home(tmp_path, monkeypatch):
    home = tmp_path / "superteam-home"
    monkeypatch.setenv("SUPERTEAM_HOME", str(home))
    return home
