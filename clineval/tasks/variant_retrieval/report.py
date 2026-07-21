"""Render a variant_retrieval EvaluationResult to Markdown (its own template).

Recall-first: the report leads with recall (did we surface the known references?)
and frames precision as contextual, then details missed evidence and unresolved
variants so nothing is silently dropped, and closes with the regulatory mapping.
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
    return template.render(
        r=result,
        provenance=provenance,
        agg=metric.aggregate,
        per_doc=metric.per_document,
        missed=metric.details.get("missed", {}),
        unresolved=metric.details.get("unresolved", []),
        rows=mapping.get_retrieval_mapping_rows(),
        disclaimer=mapping.DISCLAIMER,
    )
