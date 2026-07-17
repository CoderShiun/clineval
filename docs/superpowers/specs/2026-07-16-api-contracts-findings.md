# Variant-retrieval API contracts — Task 0 spike findings

- **Verified:** 2026-07-17, from this network (corporate egress OK).
- **Example variant:** `NM_000540.3:c.1840C>T` = `p.(Arg614Cys)`/`p.R614C` = `NC_000019.10:g.38457545C>T`
  = **`rs118192172`** (ClinVar: Pathogenic; RYR1).
- **Fixtures saved** under `tests/fixtures/api_samples/` — client unit tests mock the HTTP layer and
  parse these; **no live calls in the test suite.**

> ⚠️ **Correctness lesson (baked into the design).** `rs193922747` — an early hand-guessed
> placeholder — is a *different* RYR1 variant (`p.C35R`, 14 papers), not R614C. The real rsID
> (`rs118192172`, 86 papers) comes only from a **coordinate-derived lookup (myvariant/dbSNP)**.
> Never guess or hardcode an rsID. This also motivates the Phase-2 variant-match gate.

---

## 1. VariantValidator  ✅ (confirmed; see design spec §4.1)

- **GET** `https://rest.variantvalidator.org/VariantValidator/variantvalidator/{build}/{hgvs}/all`
  · header `Content-Type: application/json` · build `GRCh38`.
- Fixture: `variantvalidator_ryr1.json`. Top-level = variant-HGVS key + `flag` + `metadata`.
- Keys used: per-hit `hgvs_transcript_variant`; `hgvs_predicted_protein_consequence.{tlr,slr}`
  (accession-prefixed, e.g. `NP_000531.2:p.(Arg614Cys)`); `primary_assembly_loci.{grch38,...}.
  {hgvs_genomic_description,vcf}`; `gene_symbol`; `validation_warnings`.
- **Provenance:** `metadata.{variantvalidator_version, vvdb_version, vvta_version}` (e.g.
  `vvdb_version: vvdb_2025_3`). Capture into `PipelineProvenance`.

## 2. myvariant.info  ✅

- Pipeline uses the **`myvariant` Python client**: `getvariant(hgvs_or_hgvsg, fields=["dbsnp.rsid",
  "clinvar", "gnomad_genome"])`, `set_caching()`. Fixture `myvariant_ryr1.json` captured via REST
  (`GET https://myvariant.info/v1/variant/chr19:g.38457545C>T?fields=...&assembly=hg38`) for shape.
- Keys used: `dbsnp.rsid` (→ **`rs118192172`**, confirmed), `clinvar.rcv[].clinical_significance`
  (Pathogenic ×5, drug response …), `gnomad_genome.af`. Non-fatal on miss.

## 3. LitVar2  ✅ — endpoints CHANGED; flow updated (affects plan Tasks 11 & 12)

Base: `https://www.ncbi.nlm.nih.gov/research/litvar2-api`. The old `/variant/search/` path is
**gone (404)**. The working two-step flow:

**(a) Resolve a query → LitVar variant id(s).**
`GET /variant/autocomplete/?query={text}` → `200`, array of candidates:
```json
[{"_id":"litvar@rs118192172##","rsid":"rs118192172","gene":["RYR1"],"name":"p.R614C",
  "hgvs":"p.R614C","pmids_count":86, ...}]
```
Fixture: `litvar_autocomplete_ryr1.json` (query `RYR1 p.R614C`). Use `_id`; `rsid`/`gene`/`hgvs`
let us confirm the candidate really matches our variant before trusting it.

**(b) Get publications for a variant id.**
`GET /variant/get/{urlencoded _id}/publications` → `200`:
```json
{"pmids":[27646467, ...], "pmcids":["PMC...", ...], "pmids_count":86}
```
Fixture: `litvar_publications_ryr1.json`. **`pmids` are integers → coerce to `str`** in the client.
`_id` must be URL-encoded (`litvar@rs118192172##` → `litvar%40rs118192172%23%23`).

**Recall lever — a variant has MULTIPLE LitVar ids.** The same R614C resolves to both an
rsID-keyed id `litvar@rs118192172##` (**86** pmids) *and* a gene-keyed id `litvar@#6261#p.R614C`
(**7** pmids), with different pmid sets. **To maximise recall, resolve via autocomplete for the
rsID (from Stage 1) AND for gene+protein forms, keep every candidate `_id` that matches the
variant, and union publications across them.** Record which query/`_id` matched each PMID as the
`matched_form` provenance.

**Plan deltas:**
- `clients/litvar.py` (Task 11): implement `autocomplete(query) -> [candidate]` and
  `publications(_id) -> [str pmid]`; a `resolve_ids(forms, rsid, gene) -> [_id]` that filters
  candidates to genuine matches (guard against same-gene/different-variant collisions).
- `retrieve.py` (Task 12): "query per form" becomes "resolve forms/rsid → matching `_id`s → union
  publications across ids", keeping matched-form/matched-id provenance.

## 4. NCBI E-utilities (paper metadata)  ✅

- **GET** `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id={csv}`
  (+ `api_key={NCBI_API_KEY}` to raise limits 3→10 req/s). Fixture: `esummary_ryr1.json`.
- Keys used: `result.uids[]`, then `result.{pmid}.{title, fulljournalname (fallback source),
  pubdate}`. **Year = first whitespace token of `pubdate`** (e.g. `"1996 Feb"` → `1996`). Batch ids.

## 5. PubTator3  ⚪ optional (Phase-1 add-on)

- **GET** `https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson?pmids={csv}`
  → `200` BioC JSON. Fixture: `pubtator_ryr1.json`. `PubTator3[].passages[].infons.{journal,year,
  type,...}` carry title/journal/year *and* entity annotations — a possible metadata source or a
  Stage-2/3 entity signal. Heavier payload; not required for Phase-1 retrieval.

---

## Rate limiting / politeness
- NCBI (LitVar2, PubTator3, E-utilities): ~3 req/s without a key, ~10 with `NCBI_API_KEY`. Use the
  shared throttle + backoff; set the key from env; missing key → lower rate + a logged warning.
- VariantValidator / myvariant: no key; be polite; the SQLite request cache makes reruns free.

## Net effect on the plan
- Tasks 1–10, 13–18: unchanged.
- Task 11 (`litvar.py`) and Task 12 (`retrieve.py`): adopt the autocomplete→id→publications flow and
  the union-across-ids recall lever above. Endpoints are now confirmed (no more "TODO: verify path").
