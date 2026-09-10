"""
Portkey-style guardrail config loader.

Reads guardrails.yaml (GUARDRAILS_CONFIG env, default ./guardrails.yaml) and
merges it over app/defaults.py. Missing file -> defaults unchanged, so local
dev and Render work with zero config. Keeps the Rust regex hot path: this
module only declares policy, never runs matching.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def config_path() -> Path:
    return Path(os.getenv("GUARDRAILS_CONFIG", "guardrails.yaml"))


def load_file(path: Path | None = None) -> dict[str, Any]:
    p = path or config_path()
    if not p.exists():
        return {}
    try:
        import yaml  # pyyaml already in requirements
    except Exception:
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def merged_defaults() -> tuple[dict, dict, dict, dict]:
    """(input_rules, output_rules, topic_policy, compliance_rules)."""
    from app.defaults import (
        DEFAULT_COMPLIANCE,
        DEFAULT_INPUT_RULES,
        DEFAULT_OUTPUT_RULES,
        DEFAULT_TOPIC_POLICY,
    )
    import copy
    file_cfg = load_file()
    inp = copy.deepcopy(DEFAULT_INPUT_RULES)
    out = copy.deepcopy(DEFAULT_OUTPUT_RULES)
    topic = copy.deepcopy(DEFAULT_TOPIC_POLICY)
    comp = copy.deepcopy(DEFAULT_COMPLIANCE)
    for key, target in (
        ("input_rules", inp),
        ("output_rules", out),
        ("topic_policy", topic),
        ("compliance_rules", comp),
    ):
        override = file_cfg.get(key)
        if isinstance(override, dict):
            target.update(override)
    return inp, out, topic, comp
