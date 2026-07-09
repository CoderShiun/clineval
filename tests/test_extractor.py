import pytest

from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction.extractor import CachedExtractor, OpenAICompatibleExtractor


def test_cached_extractor_replays_and_reads_model(tmp_path):
    cache = tmp_path / "cache.jsonl"
    cache.write_text(
        '{"_meta": true, "model": "qwen2.5-7b (LM Studio)"}\n'
        '{"id": "r1", "system_output": ["HP_0001250", "HP:0001250"]}\n',
        encoding="utf-8",
    )
    ext = CachedExtractor(str(cache))
    assert ext.model == "qwen2.5-7b (LM Studio)"
    rec = PredictionRecord(id="r1", input_text="", gold_reference=[])
    assert ext.extract(rec) == ["HP:0001250"]  # normalized + deduped
    assert ext.extract(PredictionRecord(id="missing", input_text="", gold_reference=[])) == []


def test_cached_extractor_rejects_malformed_cache_line(tmp_path):
    cache = tmp_path / "cache.jsonl"
    cache.write_text(
        '{"_meta": true, "model": "qwen-test"}\n'
        '{"system_output": ["HP:0001250"]}\n',  # missing "id"
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="malformed cache"):
        CachedExtractor(str(cache))


def test_openai_extractor_parses_response(monkeypatch):
    class FakeMessage:
        content = "Findings: HP_0001250 and HP:0000252."

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletions:
        def create(self, **kwargs):
            class R:
                choices = [FakeChoice()]
            return R()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    ext = OpenAICompatibleExtractor.__new__(OpenAICompatibleExtractor)
    ext.client = FakeClient()
    ext.model = "local-model"
    rec = PredictionRecord(id="r1", input_text="patient text", gold_reference=[])
    assert ext.extract(rec) == ["HP:0001250", "HP:0000252"]
