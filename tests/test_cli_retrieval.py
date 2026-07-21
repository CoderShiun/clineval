import clineval.cli
from clineval.cli import _build_pipeline_retriever, app
from clineval.pipeline.models import PipelineProvenance, RetrievalResult, VariantForms
from typer.testing import CliRunner

runner = CliRunner()


def test_retrieval_eval_cached_writes_report(tmp_path):
    out = tmp_path / "retrieval.md"
    result = runner.invoke(app, [
        "retrieval-eval", "--dataset", "ryr1", "--source", "cached",
        "--cache", "examples/data/cached_retrieval.jsonl", "--report", str(out),
    ])
    assert result.exit_code == 0, result.output
    md = out.read_text(encoding="utf-8")
    assert "Variant Literature Retrieval Report" in md
    assert "Recall" in md
    assert "Unresolved variants" in md
    # The intronic seed variant must appear as unresolved (flagged, not dropped).
    assert "c.1840+1G>A" in md
    # Full cache coverage -> hit-rate provenance, no warning.
    assert "cache_hit_rate=3/3" in md
    assert "WARNING" not in result.output


def test_retrieval_eval_rejects_bad_source(tmp_path):
    result = runner.invoke(app, [
        "retrieval-eval", "--dataset", "ryr1", "--source", "bogus",
        "--report", str(tmp_path / "r.md"),
    ])
    assert result.exit_code == 1
    assert "must be cached, live, or dataset" in result.output


def test_retrieval_eval_dataset_load_error_is_friendly(tmp_path):
    result = runner.invoke(app, [
        "retrieval-eval", "--dataset", str(tmp_path / "missing.jsonl"),
        "--source", "cached", "--report", str(tmp_path / "r.md"),
    ])
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_retrieval_eval_bad_cache_is_friendly(tmp_path):
    # A missing --cache must yield a clean Error:/exit 1, not a raw traceback.
    result = runner.invoke(app, [
        "retrieval-eval", "--dataset", "ryr1", "--source", "cached",
        "--cache", str(tmp_path / "nope.jsonl"), "--report", str(tmp_path / "r.md"),
    ])
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_retrieval_eval_dataset_hgmd_branch(tmp_path, monkeypatch):
    # Cover the 'hgmd' dispatch: stub the (git-ignored, licence-gated) HGMD loader.
    from clineval.core.schema import PredictionRecord

    class StubLoader:
        def load(self):
            return [PredictionRecord(id="NM:c.1A>T", input_text="x",
                                     gold_reference=["1"], system_output=["1"])]

    monkeypatch.setattr(clineval.cli, "HgmdGoldLoader", lambda *a, **k: StubLoader())
    out = tmp_path / "r.md"
    result = runner.invoke(app, [
        "retrieval-eval", "--dataset", "hgmd", "--source", "dataset", "--report", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert "Variant Literature Retrieval Report" in out.read_text(encoding="utf-8")


def test_retrieval_eval_source_dataset(tmp_path):
    # A gold JSONL that already carries predictions; --source dataset scores them.
    data = tmp_path / "d.jsonl"
    data.write_text(
        '{"id": "NM:c.1A>T", "gold_reference": ["7"], "system_output": ["7", "8"]}\n',
        encoding="utf-8",
    )
    out = tmp_path / "r.md"
    result = runner.invoke(app, [
        "retrieval-eval", "--dataset", str(data), "--source", "dataset", "--report", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert "source: dataset" in result.output
    assert "Variant Literature Retrieval Report" in out.read_text(encoding="utf-8")


def test_retrieval_eval_partial_cache_warns(tmp_path):
    # Cache covers only one of the three seed variants -> hit-rate < 1 and a warning.
    cache = tmp_path / "partial.jsonl"
    cache.write_text(
        '{"id": "NM_000540.3:c.7300G>A", "pmids": ["99000003"], "resolved": true}\n',
        encoding="utf-8",
    )
    out = tmp_path / "r.md"
    result = runner.invoke(app, [
        "retrieval-eval", "--dataset", "ryr1", "--source", "cached",
        "--cache", str(cache), "--report", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert "1/3 variants matched cache" in result.output
    assert "cache_hit_rate=1/3" in out.read_text(encoding="utf-8")


def test_retrieval_eval_live_source(tmp_path, monkeypatch):
    # Exercise the live dispatch branch without touching the network: stub the
    # pipeline retriever so the CLI wiring (label, extract loop, report) is covered.
    class StubRetriever:
        mode = "live"

        def extract(self, rec):
            return ["99000001", "99000002"] if "1840C" in rec.id else []

    monkeypatch.setattr(clineval.cli, "_build_pipeline_retriever", lambda gb, rc: StubRetriever())
    out = tmp_path / "r.md"
    result = runner.invoke(app, [
        "retrieval-eval", "--dataset", "ryr1", "--source", "live", "--report", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert "source: live-pipeline" in result.output
    md = out.read_text(encoding="utf-8")
    assert "Variant Literature Retrieval Report" in md
    assert "genome_build=GRCh38" in md   # live runs record the build for traceability
    assert "vvdb_version=" not in md      # no per-record provenance -> no version keys


def test_retrieval_eval_live_lifts_tool_provenance(tmp_path, monkeypatch):
    # When the live pipeline records tool/DB versions per variant, the run-level report
    # must surface them (the regulatory table advertises this evidence snapshot).
    class StubRetriever:
        mode = "live"

        def extract(self, rec):
            rec.metadata["provenance"] = {
                "vvdb_version": "vvdb_2025_3",
                "sources": ["variantvalidator", "litvar2"],
            }
            return ["99000001"]

    monkeypatch.setattr(clineval.cli, "_build_pipeline_retriever", lambda gb, rc: StubRetriever())
    out = tmp_path / "r.md"
    result = runner.invoke(app, [
        "retrieval-eval", "--dataset", "ryr1", "--source", "live", "--report", str(out),
    ])
    assert result.exit_code == 0, result.output
    md = out.read_text(encoding="utf-8")
    assert "vvdb_version=vvdb_2025_3" in md
    assert "sources=variantvalidator,litvar2" in md


def test_retrieval_eval_live_network_failure_is_friendly(tmp_path, monkeypatch):
    from clineval.pipeline.clients.http import TransientHTTPError

    class BoomRetriever:
        mode = "live"

        def extract(self, rec):
            raise TransientHTTPError("connection reset")

    monkeypatch.setattr(clineval.cli, "_build_pipeline_retriever", lambda gb, rc: BoomRetriever())
    result = runner.invoke(app, [
        "retrieval-eval", "--dataset", "ryr1", "--source", "live", "--report", str(tmp_path / "r.md"),
    ])
    assert result.exit_code == 1
    assert "live retrieval failed" in result.output


def test_build_pipeline_retriever_wires_live_seams(tmp_path, monkeypatch):
    # Cover the live-wiring helper offline: stub the network client with a side
    # effect (MyVariantClient.set_caching) and both pipeline stage functions, then
    # invoke the two seams so their lambda bodies are exercised.
    import clineval.pipeline.clients.myvariant_client as mv_mod
    import clineval.pipeline.normalize as norm_mod
    import clineval.pipeline.retrieve as retr_mod

    monkeypatch.setattr(mv_mod, "MyVariantClient", lambda *a, **k: object())
    forms = VariantForms(input="NM:c.1A>T", forms=["p.R1C"], resolved=True, xrefs={},
                         notes=[], provenance=PipelineProvenance())
    monkeypatch.setattr(norm_mod, "normalize_and_expand",
                        lambda hgvs, build, *, vv, mv: forms)
    monkeypatch.setattr(retr_mod, "retrieve",
                        lambda f, *, litvar, eutils: RetrievalResult(
                            variant=f.input, pmids=["1"], papers=[], notes=[],
                            provenance=PipelineProvenance()))

    retriever = _build_pipeline_retriever("GRCh38", str(tmp_path / "req.sqlite"))
    assert retriever.mode == "live"
    got = retriever._normalize("NM:c.1A>T")     # invokes the normalize lambda
    assert got is forms
    out = retriever._retrieve(got)               # invokes the retrieve lambda
    assert out.pmids == ["1"]
