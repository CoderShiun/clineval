"""PyHPO wrapper: loading, version, ID resolution, IC and similarity access.

This is the only module that imports PyHPO. Metrics depend on this wrapper, not
on PyHPO directly, so any PyHPO API change is isolated here.
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass

from clineval.core.ontology.ic import term_ic
from clineval.core.ontology.similarity import (
    bma as _bma,
    is_ancestor_or_descendant,
    jaccard,
    pairwise,
)


@dataclass
class TermResolution:
    """Result of aligning one HPO ID against the active ontology."""

    original: str
    resolved: str | None
    status: str  # "primary" | "alt_id" | "obsolete" | "unknown"


class Ontology:
    """Loaded HPO ontology + semantic-similarity helpers."""

    _METHODS = frozenset({"resnik", "lin", "jc", "jc2", "rel", "ic", "dist", "jaccard"})

    def __init__(self, ic_basis: str = "omim") -> None:
        from pyhpo import Ontology as _PyOntology

        _PyOntology()  # initialize the PyHPO singleton (loads graph + annotations)
        self._onto = _PyOntology
        self.ic_basis = ic_basis
        self._alt_index = self._build_alt_index()

        probe = self._lookup("HP:0000118")  # "Phenotypic abnormality" (always present)
        if probe is None or getattr(probe.information_content, self.ic_basis, None) is None:
            raise ValueError(
                f"unknown ic_basis {self.ic_basis!r}; expected one of the pyhpo "
                "information_content fields (e.g. 'omim', 'gene', 'orpha', 'decipher')"
            )

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

    @property
    def library_version(self) -> str:
        # The pyhpo release bundles a specific OMIM annotation snapshot that
        # drives every IC value: the same HPO obo data-version under a
        # different pyhpo release can still yield different scores.
        return importlib.metadata.version("pyhpo")

    def _build_alt_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        try:
            for term in self._onto:
                # Skip obsolete terms so an obsolete-retained term's alt_id can
                # never resolve back to it.
                if getattr(term, "is_obsolete", False):
                    continue
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
        except RuntimeError:
            # pyhpo 4.0.0 raises RuntimeError("Unknown HPO term") for an
            # unresolvable id; any other exception is real API drift -> propagate.
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
        return TermResolution(hpo_id, None, "unknown")

    def term(self, hpo_id: str):
        return self._lookup(hpo_id)

    def ic(self, hpo_id: str) -> float:
        term = self._lookup(hpo_id)
        return term_ic(term, self.ic_basis) if term is not None else 0.0

    def similarity(self, id1: str, id2: str, method: str = "lin") -> float:
        if method not in self._METHODS:
            raise ValueError(
                f"unknown similarity method {method!r}; choose from {sorted(self._METHODS)}"
            )
        t1 = self._lookup(id1)
        if t1 is None:
            return 0.0
        t2 = t1 if id2 == id1 else self._lookup(id2)
        if t2 is None:
            return 0.0
        if method == "jaccard":
            return jaccard(t1, t2)
        if id1 == id2 and method in ("lin", "jc"):
            return 1.0
        return pairwise(t1, t2, method=method, basis=self.ic_basis)

    def bma(self, ids1: list[str], ids2: list[str], method: str = "lin") -> float:
        return _bma(self, ids1, ids2, method=method)

    def related(self, id1: str, id2: str) -> bool:
        t1, t2 = self._lookup(id1), self._lookup(id2)
        if t1 is None or t2 is None:
            return False
        return is_ancestor_or_descendant(t1, t2)
