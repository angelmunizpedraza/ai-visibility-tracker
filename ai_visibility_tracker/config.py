"""Config loading (YAML if PyYAML is installed, JSON always)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .detect import Brand


@dataclass
class Config:
    brands: List[Brand]
    prompts: List[str]
    label: Optional[str] = None


def _parse(text: str, suffix: str) -> dict:
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise ValueError("Install PyYAML to use YAML configs (pip install pyyaml) or use JSON") from e
        return yaml.safe_load(text) or {}
    return json.loads(text)


def load_config(path: str | Path) -> Config:
    p = Path(path)
    data = _parse(p.read_text(encoding="utf-8"), p.suffix.lower())
    brands_raw = data.get("brands") or []
    prompts = [str(x).strip() for x in (data.get("prompts") or []) if str(x).strip()]
    if not brands_raw:
        raise ValueError("Config needs at least one brand under 'brands'")
    if not prompts:
        raise ValueError("Config needs at least one prompt under 'prompts'")
    brands: List[Brand] = []
    for b in brands_raw:
        if isinstance(b, str):
            brands.append(Brand(name=b))
            continue
        brands.append(
            Brand(
                name=str(b["name"]),
                domains=tuple(b.get("domains") or []),
                aliases=tuple(b.get("aliases") or []),
            )
        )
    return Config(brands=brands, prompts=prompts, label=data.get("label"))
