"""Static mapping from ClinEval evidence to regulatory clauses (MVP: a table).

Not legal advice. ISO 15189 references use the 2022 edition numbering.
"""

from __future__ import annotations

DISCLAIMER = (
    "This mapping is a general technical/educational reference, not legal or "
    "regulatory-compliance advice. Clauses and timelines change; consult qualified "
    "regulatory/quality professionals against the current official texts."
)

REGULATORY_ROWS: list[dict[str, str]] = [
    {
        "evidence": "Exact P/R/F1",
        "ai_act": "Art 15 (accuracy)",
        "ivdr": "Annex XIII analytical performance",
        "iso15189": "7.3.2 verification of examination methods",
    },
    {
        "evidence": "Semantic F1 / IC-weighted",
        "ai_act": "Art 15 (appropriate accuracy metrics; robustness)",
        "ivdr": "performance evaluation",
        "iso15189": "7.3.3 validation of examination methods",
    },
    {
        "evidence": "Error taxonomy + significance flags",
        "ai_act": "Art 15 (robustness)",
        "ivdr": "performance / risk evidence",
        "iso15189": "7.3.7 ensuring validity of results + 7.5 nonconforming work (clinical significance)",
    },
    {
        "evidence": "Ontology alignment / traceability",
        "ai_act": "Art 12 (logging & traceability)",
        "ivdr": "technical documentation",
        "iso15189": "Clause 8 management system (control of records & documents)",
    },
]


def get_mapping_rows() -> list[dict[str, str]]:
    """Return a copy of the regulatory mapping rows."""
    return [dict(row) for row in REGULATORY_ROWS]


RETRIEVAL_ROWS: list[dict[str, str]] = [
    {
        "evidence": "Retrieval recall vs known references",
        "ai_act": "Art 15 (accuracy)",
        "ivdr": "Annex XIII analytical performance / performance evaluation",
        "iso15189": "7.3.3 validation of examination methods",
    },
    {
        "evidence": "Yield / precision context",
        "ai_act": "Art 15 (appropriate accuracy metrics)",
        "ivdr": "performance evaluation",
        "iso15189": "7.3.3 validation of examination methods",
    },
    {
        "evidence": "Evidence snapshot / tool-version provenance",
        "ai_act": "Art 12 (logging & traceability)",
        "ivdr": "technical documentation",
        "iso15189": "Clause 8 (control of records)",
    },
    {
        "evidence": "Unresolved-variant flagging (no silent drop)",
        "ai_act": "Art 15 (robustness)",
        "ivdr": "risk / performance evidence",
        "iso15189": "7.3.7 ensuring validity of results",
    },
]


def get_retrieval_mapping_rows() -> list[dict[str, str]]:
    """Return a copy of the variant-retrieval regulatory mapping rows."""
    return [dict(row) for row in RETRIEVAL_ROWS]
