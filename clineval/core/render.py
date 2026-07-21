"""Shared helpers for Markdown report rendering (used by every task's renderer)."""

from __future__ import annotations

from jinja2 import Environment, FileSystemLoader

from clineval.core.schema import EvaluationResult, MetricResult


def make_markdown_env(template_dir: str) -> Environment:
    """A Jinja environment tuned for Markdown: no HTML escaping, tidy block whitespace."""
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def require_metric(result: EvaluationResult, name: str) -> MetricResult:
    """Return the named metric result, or raise a clear error if the run lacks it."""
    found = result.metric(name)
    if found is None:
        raise ValueError(f"missing metric '{name}' in result")
    return found
