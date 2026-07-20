import importlib


def test_pipeline_and_task_packages_import():
    # The new packages must import cleanly (empty inits are fine).
    assert importlib.import_module("clineval.pipeline") is not None
    assert importlib.import_module("clineval.pipeline.clients") is not None
    assert importlib.import_module("clineval.tasks.variant_retrieval") is not None


def test_new_runtime_deps_present():
    # Guards against a stale uv.lock: deps declared in pyproject must be installed
    # in the image (this is what catches "added to pyproject but not `uv lock`-ed").
    assert importlib.import_module("myvariant") is not None
    assert importlib.import_module("requests") is not None
