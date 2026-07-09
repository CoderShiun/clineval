"""Normalize system/gold HPO IDs into the canonical ``HP:0000000`` form.

Pure string handling — no PyHPO. GSC+ uses underscores (``HP_0000110``) while
PyHPO uses colons (``HP:0000110``); without normalization nothing matches.
"""

from __future__ import annotations

import re
from typing import Iterable

from clineval.core.schema import OntologyAlignment, PredictionRecord

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


def _align_list(ontology, ids: list[str], counters: dict) -> list[str]:
    resolved: list[str] = []
    for hpo_id in ids:
        res = ontology.resolve(hpo_id)
        if res.status == "primary":
            resolved.append(res.resolved)
        elif res.status == "alt_id":
            counters["alt"] += 1
            resolved.append(res.resolved)
        else:  # obsolete / unknown
            counters["obsolete"] += 1
            counters["obsolete_ids"].append(hpo_id)
    seen: set[str] = set()
    deduped: list[str] = []
    for x in resolved:
        if x not in seen:
            seen.add(x)
            deduped.append(x)
    return deduped


def align_records(records: list[PredictionRecord], ontology) -> tuple[list[PredictionRecord], OntologyAlignment]:
    """Resolve alt_ids to primary and flag/drop obsolete IDs; summarize alignment."""
    counters = {"alt": 0, "obsolete": 0, "obsolete_ids": []}
    for rec in records:
        rec.gold_reference = _align_list(ontology, rec.gold_reference, counters)
        rec.system_output = _align_list(ontology, rec.system_output, counters)
    alignment = OntologyAlignment(
        hpo_version=ontology.version,
        ic_basis=ontology.ic_basis,
        alt_ids_resolved=counters["alt"],
        obsolete_flagged=counters["obsolete"],
        obsolete_ids=sorted(set(counters["obsolete_ids"])),
        policy=(
            "alt_id resolved to primary; merged/obsolete IDs flagged and excluded "
            "from scoring (no replaced_by remap in the MVP)."
        ),
    )
    return records, alignment
