"""Dataclasses passed between the pipeline stages.

Stage 1 (``normalize``) produces a ``VariantForms``; Stage 2 (``retrieve``) consumes
it and produces a ``RetrievalResult``. ``PipelineProvenance`` records tool/DB versions
and cache stats for the IVDR evidence snapshot; ``PaperRef`` is one retrieved paper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineProvenance:
    """Tool/DB versions + cache stats for the IVDR evidence snapshot."""

    vv_version: str = ""
    vvdb_version: str = ""
    vvta_version: str = ""
    sources: list[str] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass
class PaperRef:
    """One retrieved paper, with the synonym form that surfaced it (provenance)."""

    pmid: str
    title: str = ""
    journal: str = ""
    year: int | None = None
    matched_form: str = ""


@dataclass
class VariantForms:
    """Stage 1 output: every string form a paper might use to name the variant.

    ``resolved`` is False when no protein consequence could be derived (splice/
    intronic/indel/protein-only); such variants are flagged (see ``notes``) and
    kept, never dropped. ``xrefs`` carries rsID/ClinVar/gnomAD for reuse downstream.
    """

    input: str
    forms: list[str]
    resolved: bool
    xrefs: dict[str, Any]
    gene: str = ""
    notes: list[str] = field(default_factory=list)
    provenance: PipelineProvenance = field(default_factory=PipelineProvenance)


@dataclass
class RetrievalResult:
    """Stage 2 output: the deduplicated PMID union + per-paper metadata."""

    variant: str
    pmids: list[str]
    papers: list[PaperRef]
    provenance: PipelineProvenance = field(default_factory=PipelineProvenance)
    notes: list[str] = field(default_factory=list)
