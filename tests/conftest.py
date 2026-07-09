import pytest

from clineval.core.ontology.hpo import Ontology


@pytest.fixture(scope="session")
def ontology():
    """Load PyHPO once per test session (heavy: loads the HPO graph + annotations)."""
    return Ontology(ic_basis="omim")
