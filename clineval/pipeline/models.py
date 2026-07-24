"""Dataclasses passed between the pipeline stages.

Stage 1 (``normalize``) produces a ``VariantForms``; Stage 2 (``retrieve``) consumes
it and produces a ``RetrievalResult``. ``PipelineProvenance`` records tool/DB versions
+ the sources consulted for the IVDR evidence snapshot; ``PaperRef`` is one retrieved paper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineProvenance:
    """Tool/DB versions + sources consulted, for the IVDR evidence snapshot.

    (Cache hit/miss counts are deliberately not carried here: the request cache lives inside
    the shared HttpClient, out of this dataclass's reach, so an always-zero field would
    over-claim the snapshot. The evidence date is the run timestamp on the EvaluationResult.)
    """

    vv_version: str = ""
    vvdb_version: str = ""
    vvta_version: str = ""
    sources: list[str] = field(default_factory=list)


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
    ``normalization_failed`` is True when Stage 1 itself failed (e.g. a VariantValidator
    outage) — distinct from a clean "no protein consequence" — so Stage 2 can mark the
    variant's retrieval degraded rather than scoring its empty result as a real zero.
    """

    input: str
    forms: list[str]
    resolved: bool
    xrefs: dict[str, Any]
    gene: str = ""
    notes: list[str] = field(default_factory=list)
    provenance: PipelineProvenance = field(default_factory=PipelineProvenance)
    normalization_failed: bool = False


@dataclass
class RetrievalResult:
    """Stage 2 output: the deduplicated PMID union + per-paper metadata.

    ``status`` is "ok" when retrieval completed cleanly, or "degraded" when a LitVar call
    failed OR Stage 1 (normalization) itself failed (``forms.normalization_failed``) — so an
    empty ``pmids`` from an outage is never mistaken for "no literature exists" (the reason is
    also spelled out in ``notes``).
    """

    variant: str
    pmids: list[str]
    papers: list[PaperRef]
    provenance: PipelineProvenance = field(default_factory=PipelineProvenance)
    notes: list[str] = field(default_factory=list)
    status: str = "ok"
