"""Normalize system/gold HPO IDs into the canonical ``HP:0000000`` form.

Pure string handling — no PyHPO. GSC+ uses underscores (``HP_0000110``) while
PyHPO uses colons (``HP:0000110``); without normalization nothing matches.
"""

from __future__ import annotations

import re
from typing import Iterable

from clineval.core.schema import PredictionRecord

_HPO_RE = re.compile(r"HP[:_](\d{7})", re.IGNORECASE)


def normalize_hpo_id(raw: str | None) -> str | None:
    """Return canonical ``HP:0000000`` for a single ID, or None if not an HPO ID."""
    if raw is None:
        return None
    match = _HPO_RE.search(str(raw).strip())
    if not match:
        return None
    return f"HP:{match.group(1)}"


def normalize_hpo_ids(raw_ids: Iterable[str]) -> list[str]:
    """Normalize a collection: drop invalid, dedupe, preserve first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in raw_ids:
        nid = normalize_hpo_id(raw)
        if nid is not None and nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


def parse_llm_output(text: str) -> list[str]:
    """Extract HPO IDs from free-form or JSON LLM output."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for digits in _HPO_RE.findall(text):
        nid = f"HP:{digits}"
        if nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


def normalize_record(rec: PredictionRecord) -> PredictionRecord:
    """Normalize gold_reference and system_output in place; return the record."""
    rec.gold_reference = normalize_hpo_ids(rec.gold_reference)
    rec.system_output = normalize_hpo_ids(rec.system_output)
    return rec
