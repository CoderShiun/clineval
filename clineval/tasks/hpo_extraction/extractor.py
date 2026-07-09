"""System-under-test extractors. Deliberately simple — this is the evaluated
component, not the product.

Default demo path replays cached predictions (zero setup, real numbers). The
``--live`` path calls an OpenAI-compatible endpoint (LM Studio by default).
"""

from __future__ import annotations

import json

from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction import adapters

_EXTRACTION_PROMPT = (
    "You extract Human Phenotype Ontology (HPO) terms from clinical text. "
    "Return every phenotype you find as its HPO ID in the form HP:0000000, "
    "comma-separated. Output only the IDs."
)


class CachedExtractor:
    """Replay committed predictions keyed by record id."""

    def __init__(self, path: str) -> None:
        self.model = "unknown"
        self._by_id: dict[str, list[str]] = {}
        with open(path, encoding="utf-8") as fh:
            for n, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"malformed cache line {n} in {path}: {exc}") from exc
                if not isinstance(obj, dict):
                    raise ValueError(f"malformed cache line {n} in {path}: not a JSON object")
                if obj.get("_meta"):
                    self.model = obj.get("model", "unknown")
                    continue
                if "id" not in obj:
                    raise ValueError(f"malformed cache line {n} in {path}: missing required field 'id'")
                if "system_output" in obj and not isinstance(obj["system_output"], list):
                    raise ValueError(
                        f"malformed cache line {n} in {path}: field 'system_output' "
                        f"must be a list, got {type(obj['system_output']).__name__}"
                    )
                self._by_id[str(obj["id"])] = adapters.normalize_hpo_ids(
                    obj.get("system_output", [])
                )

    def extract(self, record: PredictionRecord) -> list[str]:
        return list(self._by_id.get(record.id, []))

    def covers(self, record_id: str) -> bool:
        return record_id in self._by_id


class OpenAICompatibleExtractor:
    """Call a local OpenAI-compatible endpoint (LM Studio / Ollama / vLLM)."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = "local-model",
        api_key: str = "not-needed",
    ) -> None:
        from openai import OpenAI

        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def extract(self, record: PredictionRecord) -> list[str]:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": _EXTRACTION_PROMPT},
                {"role": "user", "content": record.input_text},
            ],
        )
        text = response.choices[0].message.content or ""
        return adapters.parse_llm_output(text)
