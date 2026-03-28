from __future__ import annotations

import logging
from dataclasses import fields
from pathlib import Path
from typing import Any
import tomllib

logger = logging.getLogger(__name__)

from superteam.core.session import superteam_home


def load_global_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or (superteam_home() / "config.toml")
    if not config_path.exists():
        return {}
    return tomllib.loads(config_path.read_text(encoding="utf-8"))


def deep_merge(*items: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for item in items:
        if not item:
            continue
        for key, value in item.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = value
    return merged


def filter_dataclass_kwargs(cls: type, values: dict[str, Any]) -> dict[str, Any]:
    valid = {f.name for f in fields(cls)}
    filtered = {}
    unknown = []
    for key, value in values.items():
        if key in valid:
            filtered[key] = value
        else:
            unknown.append(key)
    if unknown:
        logger.warning(
            "Unknown config keys for %s will be ignored: %s",
            cls.__name__,
            ", ".join(sorted(unknown)),
        )
    return filtered
