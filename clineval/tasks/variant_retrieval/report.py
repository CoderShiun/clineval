"""Render a variant_retrieval EvaluationResult to Markdown (its own template).

Concordance-framed: the report shows macro AND micro recall together with the
HGMD-ceiling caveat (these are concordance-with-HGMD scores, not evidence coverage),
details missed evidence, unresolved variants, and any degraded retrieval so nothing is
silently dropped or over-trusted, and closes with the regulatory mapping.
"""

from __future__ import annotations

from pathlib import Path

from clineval.core.render import make_markdown_env, require_metric
from clineval.core.schema import EvaluationResult
from clineval.regulatory import mapping

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


def render_retrieval_report(result: EvaluationResult) -> str:
    """Return the Markdown report for a variant_retrieval evaluation result."""
    metric = require_metric(result, "retrieval_prf")
    env = make_markdown_env(str(_TEMPLATE_DIR))
    template = env.get_template("retrieval_report.md.j2")
    # Pre-join provenance so the template line ends in an expression, not a block tag —
    # otherwise trim_blocks eats the newline and glues the next heading onto the bullet.
    provenance = ", ".join(f"{k}={v}" for k, v in result.provenance.items())
    # The metric EXCLUDES degraded variants (API failure / cache miss) from the scores; list
    # them so their absence from the aggregates is explicit, not silent.
    degraded = metric.details.get("degraded", [])
    return template.render(
        r=result,
        provenance=provenance,
        agg=metric.aggregate,
        per_doc=metric.per_document,
        missed=metric.details.get("missed", {}),
        unresolved=metric.details.get("unresolved", []),
        degraded=degraded,
        rows=mapping.get_retrieval_mapping_rows(),
        disclaimer=mapping.DISCLAIMER,
    )
