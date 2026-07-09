# Known relationships used across tests:
#   HP:0001629 Ventricular septal defect (parent)
#   HP:0011682 Perimembranous VSD  (child of 0001629)
#   HP:0011623 Muscular VSD        (child of 0001629; sibling of 0011682)
#   HP:0001250 Seizure             (unrelated to the VSD subtree)
#   HP:0000118 Phenotypic abnormality (very broad -> low IC)


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
