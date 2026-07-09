# ClinEval

**Open-source, self-hostable evaluation toolkit for clinical LLM outputs.** ClinEval is an *evaluator* — an inspection rig for clinical AI — not a system that builds extraction or generation models. It produces clinically meaningful quality metrics **and** evidence mapped to medical-device regulation (EU AI Act, IVDR, ISO 15189:2022).

**Module A (this MVP): HPO extraction evaluation.** Given clinical text, a system's extracted HPO term IDs, and a gold standard, ClinEval scores precision/recall/F1 (exact), semantic/hierarchy-aware similarity (via PyHPO), and a clinical error taxonomy — then renders a Markdown report including a regulatory-evidence mapping.

> **Disclaimer:** General technical/educational reference, not legal or regulatory-compliance advice. Confirm dataset licenses before use and consult qualified regulatory/quality professionals against current official texts.

## Quickstart (Docker — no host installs)

```bash
docker compose build
docker compose run --rm clineval uv run clineval run --dataset synthetic --report reports/report.md
```

For a live run against a local LM Studio on the host, add `--live --base-url http://host.docker.internal:1234/v1`.
See `examples/hpo_extraction_demo.ipynb` for a notebook walkthrough.

## License

MIT — see `LICENSE`.
