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


def test_cached_extractor_rejects_invalid_json_line(tmp_path):
    cache = tmp_path / "cache.jsonl"
    cache.write_text(
        '{"_meta": true, "model": "qwen-test"}\n'
        "not json\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="malformed cache line 2"):
        CachedExtractor(str(cache))


def test_cached_extractor_rejects_non_list_system_output(tmp_path):
    cache = tmp_path / "cache.jsonl"
    cache.write_text(
        '{"_meta": true, "model": "qwen-test"}\n'
        '{"id": "r1", "system_output": "HP:0001250"}\n',  # not a list
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="malformed cache"):
        CachedExtractor(str(cache))


def test_cached_extractor_skips_blank_lines(tmp_path):
    cache = tmp_path / "cache.jsonl"
    cache.write_text(
        '{"_meta": true, "model": "qwen-test"}\n'
        "\n"  # blank line must be skipped, not raise
        '{"id": "r1", "system_output": ["HP:0001250"]}\n'
        "   \n"  # whitespace-only line also skipped
        '{"id": "r2", "system_output": ["HP:0000252"]}\n',
        encoding="utf-8",
    )
    ext = CachedExtractor(str(cache))
    assert ext.covers("r1") is True
    assert ext.covers("r2") is True


def test_cached_extractor_covers_reflects_known_ids(tmp_path):
    cache = tmp_path / "cache.jsonl"
    cache.write_text('{"id": "r1", "system_output": ["HP:0001250"]}\n', encoding="utf-8")
    ext = CachedExtractor(str(cache))
    assert ext.covers("r1") is True
    assert ext.covers("missing") is False


def test_cached_extractor_defaults_model_to_unknown_without_meta_line(tmp_path):
    cache = tmp_path / "cache.jsonl"
    cache.write_text('{"id": "r1", "system_output": ["HP:0001250"]}\n', encoding="utf-8")
    ext = CachedExtractor(str(cache))
    assert ext.model == "unknown"


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


def test_openai_extractor_init_builds_client_via_openai_module(monkeypatch):
    # Exercises the real __init__ (not __new__): monkeypatch openai.OpenAI itself
    # so construction never touches the network.
    calls = {}

    class FakeOpenAI:
        def __init__(self, base_url, api_key):
            calls["base_url"] = base_url
            calls["api_key"] = api_key

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    ext = OpenAICompatibleExtractor(
        base_url="http://example.invalid/v1", model="my-model", api_key="secret"
    )
    assert isinstance(ext.client, FakeOpenAI)
    assert ext.model == "my-model"
    assert calls == {"base_url": "http://example.invalid/v1", "api_key": "secret"}
