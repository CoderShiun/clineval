# Known relationships used across tests:
#   HP:0001629 Ventricular septal defect (parent)
#   HP:0011682 Perimembranous VSD  (child of 0001629)
#   HP:0011623 Muscular VSD        (child of 0001629; sibling of 0011682)
#   HP:0001250 Seizure             (unrelated to the VSD subtree)
#   HP:0000118 Phenotypic abnormality (very broad -> low IC)

import pytest


def test_version_is_nonempty(ontology):
    assert isinstance(ontology.version, str) and ontology.version


def test_resolve_primary(ontology):
    res = ontology.resolve("HP:0001629")
    assert res.status == "primary"
    assert res.resolved == "HP:0001629"


def test_resolve_unknown_id(ontology):
    res = ontology.resolve("HP:0000000")  # not a real term
    assert res.status == "unknown"
    assert res.resolved is None


def test_ic_specific_higher_than_broad(ontology):
    assert ontology.ic("HP:0011682") > ontology.ic("HP:0000118")


def test_lin_self_is_one(ontology):
    assert ontology.similarity("HP:0001250", "HP:0001250", method="lin") == 1.0


def test_siblings_more_similar_than_unrelated(ontology):
    sib = ontology.similarity("HP:0011682", "HP:0011623", method="lin")
    unrel = ontology.similarity("HP:0011682", "HP:0001250", method="lin")
    assert sib > unrel


def test_ancestor_relationship(ontology):
    assert ontology.related("HP:0011682", "HP:0001629") is True   # child/parent
    assert ontology.related("HP:0011682", "HP:0011623") is False  # siblings


def test_bma_perfect_and_partial(ontology):
    assert ontology.bma(["HP:0001250"], ["HP:0001250"]) == 1.0
    partial = ontology.bma(["HP:0011682"], ["HP:0011623"])
    assert 0.0 < partial < 1.0


def test_resolve_flags_obsolete_retained_term(ontology):
    # HP:0000057 is obsolete but retained in the ontology (replaced_by HP:0008665).
    res = ontology.resolve("HP:0000057")
    assert res.status == "obsolete"
    assert res.resolved is None


def test_resolve_alt_id_real(ontology):
    # HP:0004715 is a secondary (alt) id whose primary is HP:0000003.
    res = ontology.resolve("HP:0004715")
    assert res.status == "alt_id"
    assert res.resolved == "HP:0000003"


@pytest.mark.parametrize("method", ["resnik", "lin", "jc", "jaccard"])
def test_similarity_methods_nonzero_for_siblings(ontology, method):
    # Perimembranous vs muscular VSD share the specific VSD parent -> every method > 0.
    assert ontology.similarity("HP:0011682", "HP:0011623", method=method) > 0.0


def test_jaccard_self_is_one(ontology):
    assert ontology.similarity("HP:0001250", "HP:0001250", method="jaccard") == 1.0


def test_unknown_method_raises(ontology):
    with pytest.raises(ValueError):
        ontology.similarity("HP:0001250", "HP:0001250", method="bogus")


def test_similarity_unknown_id_is_zero(ontology):
    assert ontology.similarity("HP:9999999", "HP:9999999", method="lin") == 0.0


def test_bad_ic_basis_raises():
    from clineval.core.ontology.hpo import Ontology
    with pytest.raises(ValueError):
        Ontology(ic_basis="not_a_basis")


def test_term_returns_pyhpo_object(ontology):
    term = ontology.term("HP:0001629")
    assert term is not None
    assert term.id == "HP:0001629"


def test_term_returns_none_for_unknown(ontology):
    assert ontology.term("HP:9999999") is None


def test_ic_direct_value_for_known_term(ontology):
    assert ontology.ic("HP:0011682") > 0.0


def test_ic_unknown_term_is_zero(ontology):
    assert ontology.ic("HP:9999999") == 0.0


def test_similarity_zero_when_second_id_unknown(ontology):
    # id1 resolves fine; id2 does not -> must be 0.0, not an error.
    assert ontology.similarity("HP:0001629", "HP:9999999", method="lin") == 0.0


def test_related_false_when_second_id_unknown(ontology):
    assert ontology.related("HP:0001629", "HP:9999999") is False


def test_related_false_for_same_term(ontology):
    # A term is not considered an ancestor/descendant of itself.
    assert ontology.related("HP:0011682", "HP:0011682") is False


def test_bma_zero_when_one_side_empty(ontology):
    assert ontology.bma([], ["HP:0001250"]) == 0.0
    assert ontology.bma(["HP:0001250"], []) == 0.0


def test_resolve_by_name_falls_back_to_alt_id_status(ontology):
    # PyHPO resolves by human-readable name too; the name itself is not in our
    # alt_id index, so this exercises the final term.id != hpo_id fallback branch.
    res = ontology.resolve("Seizure")
    assert res.status == "alt_id"
    assert res.resolved == "HP:0001250"


class _FakeTerm:
    def __init__(self, id_, alt_id=None, is_obsolete=False):
        self.id = id_
        self.alt_id = alt_id or []
        self.is_obsolete = is_obsolete


def test_alt_index_skips_obsolete_terms_alt_ids(ontology, monkeypatch):
    # Directly exercises the documented contract: an obsolete term's alt_id must
    # never populate the index (it must not resolve back to the obsolete term).
    fake_terms = [
        _FakeTerm("HP:0000057", alt_id=["HP:0000057ALT"], is_obsolete=True),
        _FakeTerm("HP:0001250", alt_id=["HP:0001250ALT"], is_obsolete=False),
    ]
    monkeypatch.setattr(type(ontology._onto), "__iter__", lambda self: iter(fake_terms))
    index = ontology._build_alt_index()
    assert index.get("HP:0001250ALT") == "HP:0001250"
    assert "HP:0000057ALT" not in index


def test_build_alt_index_swallows_iteration_error(ontology, monkeypatch):
    def boom(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(type(ontology._onto), "__iter__", boom)
    # Defensive except must swallow the error and return an empty index rather
    # than raising out of __init__.
    assert ontology._build_alt_index() == {}


def test_version_falls_back_to_unknown_when_no_data_version_line(ontology, monkeypatch):
    import pyhpo.parser.obo as obo

    monkeypatch.setattr(obo.Metadata, "header", ["format-version: 1.2"])
    assert ontology.version == "unknown"


def test_version_falls_back_when_metadata_access_raises(ontology, monkeypatch):
    import pyhpo.parser.obo as obo

    class NoHeader:
        pass

    monkeypatch.setattr(obo, "Metadata", NoHeader)
    assert ontology.version == "unknown"


def test_version_uses_callable_pyhpo_version_when_available(ontology, monkeypatch):
    import pyhpo
    import pyhpo.parser.obo as obo

    class NoHeader:
        pass

    monkeypatch.setattr(obo, "Metadata", NoHeader)
    monkeypatch.setattr(pyhpo.Ontology, "version", lambda: "9.9.9", raising=False)
    assert ontology.version == "9.9.9"


def test_version_falls_back_to_unknown_when_callable_version_raises(ontology, monkeypatch):
    import pyhpo
    import pyhpo.parser.obo as obo

    class NoHeader:
        pass

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(obo, "Metadata", NoHeader)
    monkeypatch.setattr(pyhpo.Ontology, "version", boom, raising=False)
    assert ontology.version == "unknown"


# --- Pure-function tests for the small helper modules (no ontology fixture needed) ---


def test_term_ic_none_information_content_is_zero():
    from clineval.core.ontology.ic import term_ic

    class NoIC:
        pass

    assert term_ic(NoIC(), "omim") == 0.0


def test_term_ic_reads_dict_shaped_information_content():
    from clineval.core.ontology.ic import term_ic

    class DictIC:
        information_content = {"omim": 5.5}

    assert term_ic(DictIC(), "omim") == 5.5


def test_term_ic_missing_basis_is_zero():
    from clineval.core.ontology.ic import term_ic

    class DictIC:
        information_content = {"gene": 1.0}

    assert term_ic(DictIC(), "omim") == 0.0


def test_pairwise_falls_back_to_keyword_only_signature():
    from clineval.core.ontology.similarity import pairwise

    class KeywordOnlyTerm:
        def similarity_score(self, *, other, kind, method):
            return 0.42

    t = KeywordOnlyTerm()
    assert pairwise(t, t, method="lin", basis="omim") == 0.42
