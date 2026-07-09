"""PyHPO wrapper: loading, version, ID resolution, IC and similarity access.

This is the only module that imports PyHPO. Metrics depend on this wrapper, not
on PyHPO directly, so any PyHPO API change is isolated here.
"""

from __future__ import annotations

from dataclasses import dataclass

from clineval.core.ontology.ic import term_ic
from clineval.core.ontology.similarity import (
    bma as _bma,
    is_ancestor_or_descendant,
    pairwise,
)


@dataclass
class TermResolution:
    """Result of aligning one HPO ID against the active ontology."""

    original: str
    resolved: str | None
    status: str  # "primary" | "alt_id" | "obsolete"


class Ontology:
    """Loaded HPO ontology + semantic-similarity helpers."""

    def __init__(self, ic_basis: str = "omim") -> None:
        from pyhpo import Ontology as _PyOntology

        _PyOntology()  # initialize the PyHPO singleton (loads graph + annotations)
        self._onto = _PyOntology
        self.ic_basis = ic_basis
        self._alt_index = self._build_alt_index()

    @property
    def version(self) -> str:
        # PyHPO 4.0.0 has no `Ontology.version` attribute; the loaded release
        # is only recorded as a raw OBO header line ("data-version: ...")
        # captured by the internal obo parser during `_PyOntology()` init.
        try:
            from pyhpo.parser.obo import Metadata

            for line in Metadata.header:
                if line.startswith("data-version:"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        raw = getattr(self._onto, "version", None)
        if callable(raw):
            try:
                return str(raw())
            except Exception:
                return "unknown"
        return str(raw) if raw else "unknown"

    def _build_alt_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        try:
            for term in self._onto:
                # PyHPO 4.0.0 exposes secondary/legacy IDs as `alt_id`
                # (the brief's original `alternative_ids` does not exist).
                for alt in getattr(term, "alt_id", None) or []:
                    index[str(alt)] = term.id
        except Exception:
            pass
        return index

    def _lookup(self, hpo_id: str):
        try:
            return self._onto.get_hpo_object(hpo_id)
        except Exception:
            return None

    def resolve(self, hpo_id: str) -> TermResolution:
        term = self._lookup(hpo_id)
        if term is not None and getattr(term, "is_obsolete", False):
            # PyHPO 4.0.0 retains obsolete terms (often with a `replaced_by`
            # pointer) instead of dropping them. Per the MVP alignment
            # policy we flag these as obsolete rather than remapping via
            # `replaced_by`.
            return TermResolution(hpo_id, None, "obsolete")
        if term is not None and term.id == hpo_id:
            return TermResolution(hpo_id, hpo_id, "primary")
        if hpo_id in self._alt_index:
            return TermResolution(hpo_id, self._alt_index[hpo_id], "alt_id")
        if term is not None and term.id != hpo_id:
            return TermResolution(hpo_id, term.id, "alt_id")
        return TermResolution(hpo_id, None, "obsolete")

    def term(self, hpo_id: str):
        return self._lookup(hpo_id)

    def ic(self, hpo_id: str) -> float:
        term = self._lookup(hpo_id)
        return term_ic(term, self.ic_basis) if term is not None else 0.0

    def similarity(self, id1: str, id2: str, method: str = "lin") -> float:
        if id1 == id2:
            return 1.0 if method in ("lin", "jc") else self.ic(id1)
        t1, t2 = self._lookup(id1), self._lookup(id2)
        if t1 is None or t2 is None:
            return 0.0
        return pairwise(t1, t2, method=method, basis=self.ic_basis)

    def bma(self, ids1: list[str], ids2: list[str], method: str = "lin") -> float:
        return _bma(self, ids1, ids2, method=method)

    def related(self, id1: str, id2: str) -> bool:
        t1, t2 = self._lookup(id1), self._lookup(id2)
        if t1 is None or t2 is None:
            return False
        return is_ancestor_or_descendant(t1, t2)
