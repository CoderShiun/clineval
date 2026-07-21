"""Render an EvaluationResult to a Markdown report via Jinja2."""

from __future__ import annotations

from pathlib import Path

from clineval.core.render import make_markdown_env, require_metric
from clineval.core.schema import EvaluationResult
from clineval.regulatory import mapping

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def render_report(result: EvaluationResult) -> str:
    """Return the Markdown report for an evaluation result."""
    env = make_markdown_env(str(_TEMPLATE_DIR))
    template = env.get_template("report.md.j2")
    tier1 = require_metric(result, "tier1_exact")
    tier2 = require_metric(result, "tier2_semantic")
    tier3 = require_metric(result, "tier3_clinical")
    exact_f1 = tier1.aggregate.get("f1", 0.0)
    sem_f1 = tier2.aggregate.get("sem_f1", 0.0)
    obsolete_ids = result.alignment.obsolete_ids
    obsolete_suffix = f" ({', '.join(obsolete_ids)})" if obsolete_ids else ""
    unknown_ids = result.alignment.unknown_ids
    unknown_suffix = f" ({', '.join(unknown_ids)})" if unknown_ids else ""
    return template.render(
        r=result,
        tier1=tier1,
        tier2=tier2,
        tier3=tier3,
        exact_f1=exact_f1,
        sem_f1=sem_f1,
        gap=sem_f1 - exact_f1,
        rows=mapping.get_mapping_rows(),
        disclaimer=mapping.DISCLAIMER,
        obsolete_suffix=obsolete_suffix,
        unknown_suffix=unknown_suffix,
    )
