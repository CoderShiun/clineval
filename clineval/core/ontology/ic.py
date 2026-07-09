"""Information Content access (delegates to PyHPO term annotations)."""

from __future__ import annotations


def term_ic(term: object, basis: str) -> float:
    """IC for a PyHPO term under the given annotation basis ('omim' or 'gene')."""
    ic = getattr(term, "information_content", None)
    if ic is None:
        return 0.0
    value = getattr(ic, basis, None)
    if value is None and isinstance(ic, dict):
        value = ic.get(basis)
    return float(value) if value is not None else 0.0
