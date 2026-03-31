from dataclasses import dataclass

from superteam.runtime.config import deep_merge, filter_dataclass_kwargs, load_global_config


def test_deep_merge_nested():
    a = {"modules": {"codex": {"model": "old"}}, "loop": {"max": 5}}
    b = {"modules": {"codex": {"profile": "default"}}, "loop": {"max": 10}}
    result = deep_merge(a, b)
    assert result == {
        "modules": {"codex": {"model": "old", "profile": "default"}},
        "loop": {"max": 10},
    }


def test_deep_merge_none_items():
    assert deep_merge(None, {"a": 1}, None) == {"a": 1}


def test_deep_merge_override_scalar():
    assert deep_merge({"x": 1}, {"x": 2}) == {"x": 2}


def test_load_global_config_missing_file(tmp_path):
    assert load_global_config(tmp_path / "nope.toml") == {}


def test_load_global_config_reads_toml(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[modules.codex]\nmodel = "gpt-5-codex"\n')
    result = load_global_config(cfg)
    assert result["modules"]["codex"]["model"] == "gpt-5-codex"


def test_filter_dataclass_kwargs():
    @dataclass
    class Cfg:
        model: str = "default"
        temp: float = 0.0

    result = filter_dataclass_kwargs(Cfg, {"model": "custom", "unknown": True, "temp": 0.5})
    assert result == {"model": "custom", "temp": 0.5}


def test_filter_dataclass_kwargs_warns_on_unknown(caplog):
    import logging

    @dataclass
    class Cfg:
        model: str = "default"

    with caplog.at_level(logging.WARNING):
        result = filter_dataclass_kwargs(Cfg, {"model": "custom", "tempertaure": 0.5})
    assert result == {"model": "custom"}
    assert "tempertaure" in caplog.text
