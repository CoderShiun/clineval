"""Pairwise and set-based semantic similarity (delegates pairwise to PyHPO)."""

from __future__ import annotations


def pairwise(term1: object, term2: object, method: str = "lin", basis: str = "omim") -> float:
    """Pairwise similarity between two PyHPO terms via the given method."""
    try:
        return float(term1.similarity_score(term2, kind=basis, method=method))
    except TypeError:
        # Fallback for a keyword-only signature variant.
        return float(term1.similarity_score(other=term2, kind=basis, method=method))


def bma(ontology: object, ids1: list[str], ids2: list[str], method: str = "lin") -> float:
    """Best-Match Average between two ID sets, using ontology.similarity."""
    if not ids1 or not ids2:
        return 0.0

    def best(a: str, group: list[str]) -> float:
        return max((ontology.similarity(a, b, method=method) for b in group), default=0.0)

    precision = sum(best(a, ids2) for a in ids1) / len(ids1)
    recall = sum(best(b, ids1) for b in ids2) / len(ids2)
    return (precision + recall) / 2


def _ancestors(term: object) -> set[str]:
    seen: set[str] = set()
    stack = list(getattr(term, "parents", []) or [])
    while stack:
        node = stack.pop()
        if node.id in seen:
            continue
        seen.add(node.id)
        stack.extend(getattr(node, "parents", []) or [])
    return seen


def is_ancestor_or_descendant(term1: object, term2: object) -> bool:
    """True if one term is a (transitive) parent of the other."""
    if term1.id == term2.id:
        return False
    return term2.id in _ancestors(term1) or term1.id in _ancestors(term2)


def jaccard(term1: object, term2: object) -> float:
    """Jaccard overlap of the two terms' ancestor sets (each set includes the term itself)."""
    a = _ancestors(term1) | {term1.id}
    b = _ancestors(term2) | {term2.id}
    union = a | b
    if not union:  # pragma: no cover
        # Structurally unreachable: `a` always contains at least `{term1.id}`,
        # so `union` can never be empty for any real PyHPO term. Kept as a
        # defensive guard against a term whose `.id` construction changes.
        return 0.0
    return len(a & b) / len(union)
