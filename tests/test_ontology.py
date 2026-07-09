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


def test_resolve_obsolete_or_unknown(ontology):
    res = ontology.resolve("HP:0000000")  # not a real term
    assert res.status == "obsolete"
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
