"""Generate the string forms papers actually use to name a variant.

Half the recall problem: VariantValidator gives ``NP_000531.2:p.(Arg614Cys)``; papers
write ``p.Arg614Cys``, ``Arg614Cys``, ``R614C``, ``p.R614C``, ``p.(R614C)``. We generate
all of them — but ONLY for a clean single-residue substitution, so a frameshift/indel
never yields a misleading missense form.
"""

from __future__ import annotations

import re

AA_3TO1 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q",
    "Glu": "E", "Gly": "G", "His": "H", "Ile": "I", "Leu": "L", "Lys": "K",
    "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
    "Tyr": "Y", "Val": "V", "Ter": "*",
}
_AA_1TO3 = {v: k for k, v in AA_3TO1.items()}

# A COMPLETE single substitution: optional '(' around refAA + position + altAA, in
# 3- or 1-letter (alt may be a stop '*'/'Ter'). Applied with fullmatch (below), so any
# trailing junk — 'fs*16', 'del', synonymous '=' — is rejected.
_SUB_RE = re.compile(
    r"p\.\(?"
    r"(?P<ref>[A-Z][a-z]{2}|[A-Z])"
    r"(?P<pos>\d+)"
    r"(?P<alt>[A-Z][a-z]{2}|[A-Z]|\*)"
    r"\)?"
)


def _to3(aa: str) -> str | None:
    """Three-letter form of an amino acid (accepts 3- or 1-letter); None if unknown."""
    if aa in AA_3TO1:
        return aa
    return _AA_1TO3.get(aa)


def _to1(aa: str) -> str | None:
    """Single-letter form of an amino acid (accepts 3- or 1-letter); None if unknown."""
    if aa in AA_3TO1:
        return AA_3TO1[aa]
    return aa if aa in _AA_1TO3 else None


def protein_variants(hgvs_p: str) -> list[str]:
    """Every naming variant of a single-substitution protein HGVS; [] if it isn't one."""
    hgvs_p = hgvs_p.strip()   # strip once so the accession half is clean too
    if not hgvs_p:
        return []
    accession, protein = hgvs_p.split(":", 1) if ":" in hgvs_p else ("", hgvs_p)
    m = _SUB_RE.fullmatch(protein.strip())
    if not m:
        return []
    ref3, alt3 = _to3(m["ref"]), _to3(m["alt"])
    ref1, alt1 = _to1(m["ref"]), _to1(m["alt"])
    if not (ref3 and alt3 and ref1 and alt1):
        return []
    pos = m["pos"]
    cores = {f"{ref3}{pos}{alt3}", f"{ref1}{pos}{alt1}"}
    out: set[str] = set()
    for core in cores:
        out.add(core)                      # Arg614Cys / R614C
        out.add(f"p.{core}")               # p.Arg614Cys
        out.add(f"p.({core})")             # p.(Arg614Cys)
        if accession:
            out.add(f"{accession}:p.({core})")
            out.add(f"{accession}:p.{core}")
    return sorted(out)


def vcf_form(chrom: str, pos: str, ref: str, alt: str) -> str:
    """A ``chr-pos-ref-alt`` string, e.g. ``19-38457545-C-T``."""
    return f"{chrom}-{pos}-{ref}-{alt}"
