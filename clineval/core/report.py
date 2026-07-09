"""Render an EvaluationResult to a Markdown report via Jinja2."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from clineval.core.schema import EvaluationResult, MetricResult
from clineval.regulatory import mapping

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def _metric(result: EvaluationResult, name: str) -> MetricResult:
    found = result.metric(name)
    if found is None:
        raise ValueError(f"missing metric '{name}' in result")
    return found


def render_report(result: EvaluationResult) -> str:
    """Return the Markdown report for an evaluation result."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.md.j2")
    tier1 = _metric(result, "tier1_exact")
    tier2 = _metric(result, "tier2_semantic")
    tier3 = _metric(result, "tier3_clinical")
    exact_f1 = tier1.aggregate.get("f1", 0.0)
    sem_f1 = tier2.aggregate.get("sem_f1", 0.0)
    obsolete_ids = result.alignment.obsolete_ids
    obsolete_suffix = f" ({', '.join(obsolete_ids)})" if obsolete_ids else ""
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
    )
