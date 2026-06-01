# Phase 0 — Discovery & Acquisition (Design v1)

*Created: 2026-05-06*
*Status: implemented in scripts/search/{discover,fetch_oa,fetcher}.py*

---

## Purpose

Extend the pipeline upstream of the existing Phase 1 (PDF → evidence units), so the
end-to-end story becomes "research query → catalyst database" instead of
"PDF-in-hand → catalyst database". This is the differentiator that lines up
with the AI-materials automation-platform direction expected by PI evaluators
of the lit-mining work; it also removes the largest OSS-adoption barrier
(other groups don't have to wire up their own PDF acquisition infrastructure
before they can try the pipeline).

---

## Scope

**In scope:**
- topic / query / seed-DOI → ranked candidate list (with abstract, OA URL,
  citation count, LLM relevance)
- Open-Access PDF fetch (Unpaywall, OpenAlex `oa_url`, arXiv, ChemRxiv)
- A pluggable `PaperFetcher` interface so private institutional fetchers
  (paper-fetcher-mcp) can be plugged in without polluting OSS

**Out of scope (deliberately):**
- Paywall bypass / Sci-Hub mirroring / publisher TOS-violating scraping
- Automatic literature-review synthesis (Topanga's academic-research skill
  already covers this; we are not building a competing generic tool)
- Re-implementing OpenAlex / S2 wrappers that already exist in
  `scripts/search/search_openalex.py` and `scripts/search/semantic_scholar.py`

---

## Design decisions

The four substantive choices were settled in conversation on 2026-05-06.
This document captures the decisions and their rationale for future agents.

### Q1: Entry point (chosen: C — query AND seed-DOI)

- Both modes supported in `discover.py`:
  - `--query "..."` → OpenAlex search → top-K seeds
  - `--seed-doi 10.xxx 10.yyy ...` → use as seeds directly
  - Combining both is allowed and intentional (CLI seed augments search seeds)

**Why both, not one:** the query path matches how a domain newcomer (or a PI
demo) would use the tool. The seed-DOI path matches the long-term Branch D
"seed papers → auto-expanded database" workflow. Same pipeline, two entry
points.

### Q2: OA coverage (chosen: B — Unpaywall + arXiv + ChemRxiv)

OA sources probed in this order in `fetch_oa.py::OAFetcher`:
1. `openalex` — `Candidate.oa_url` (already on the candidate from discover.py)
2. `unpaywall` — `best_oa_location.url_for_pdf`
3. `arxiv` — title-match search via the arXiv API
4. `chemrxiv` — title-match search via the Cambridge Open Engage API

Each source: timeout, polite rate limit, PDF magic-byte sanity check before
writing. Failures fall through to the next source; if all fail, the candidate
is logged to `data/04_search/manual_queue_<date>.jsonl` for an optional
institutional fetcher to handle later.

**Not (a) only:** Unpaywall alone misses recent preprints; the +20% coverage
from arXiv / ChemRxiv is meaningful for catalysis-adjacent ML-method papers.

**Not (c) publisher-page scraping:** drifts toward TOS-violation territory
without strong coverage gain.

### Q3: Ranking (chosen: C — LLM relevance scoring)

`discover.py::_score_with_claude` scores each candidate's
title + abstract + venue against the user's query on a 0.0–1.0 scale via
Claude Haiku 4.5. Cost is ~$0.0005 per candidate (≈$0.05 per 100-candidate
discovery run). Falls back to citation × recency ranking when:
- `--no-llm` flag is set
- `ANTHROPIC_API_KEY` is missing
- The `anthropic` SDK is not installed

Caching by `(query_hash, doi)` keeps re-runs free.

**Not (a) OpenAlex relevance:** decent for raw search hits but does not
generalize to citation-expansion candidates that arrived without a search-
relevance score attached.

**Not (b) citation × recency:** used only as a fallback. As a primary signal
it overweights well-cited but off-topic survey papers.

### Q4: Institutional fetcher integration (chosen: C — interface-based)

`fetcher.py` defines the `PaperFetcher` Protocol with `can_fetch(c)` and
`fetch(c, dest_dir) → FetchResult`. `OAFetcher` is the default OSS impl.
A private `InstitutionalFetcher` (wrapping `paper-fetcher-mcp` for Utrecht
SSO) is the planned plug-in: it will sit *behind* the `OAFetcher`, picking
up entries that the OA fetcher routed to `manual_queue_*.jsonl`.

The plug-in is **not committed to the OSS repo** — OSS users do not have
the institutional access it depends on, so shipping it would only confuse.

---

## Pipeline placement

```
Phase 0 — Discovery & Acquisition (NEW)
─────────────────────────────────────────────
  query / seed-DOI
       │
       ▼  scripts/search/discover.py
  OpenAlex search + S2 references / citations / recommendations
       │
       │  Stage C: enrich (OpenAlex DOI lookup for abstract + oa_url)
       │  Stage D: Claude Haiku 4.5 relevance score (--no-llm to skip)
       │
       ▼
  data/04_search/discover_<slug>_<date>.jsonl   (ranked Candidate JSONL)
       │
       ▼  scripts/search/fetch_oa.py
  OA-only PDF download (Unpaywall → OpenAlex → arXiv → ChemRxiv)
       │            └─→ data/04_search/manual_queue_<date>.jsonl
       │                  (for InstitutionalFetcher plug-in to pick up)
       ▼
  topics/<topic>/pdfs/<sanitized_doi>.pdf
─────────────────────────────────────────────
       │
       ▼  Phase 1 takes over (existing — see STRUCTURE.md)
```

---

## File layout introduced by Phase 0

```
scripts/search/
├── discover.py          ← NEW orchestrator (Stage A–E)
├── fetch_oa.py          ← NEW OA-only fetcher (default backend)
├── fetcher.py           ← NEW PaperFetcher interface + dataclasses
├── search_openalex.py   ← existing — still callable standalone
├── semantic_scholar.py  ← existing — still callable standalone
└── s2_abstract_dryrun.py← existing — measurement tool
```

```
data/04_search/
├── discover_<slug>_<date>.jsonl   ← Phase 0 stage E output
├── fetch_log_<date>.jsonl         ← per-paper fetch outcome
├── manual_queue_<date>.jsonl      ← OA-fail papers for plug-in fetcher
└── .cache/                        ← OpenAlex / S2 / LLM response cache (24 h)
```

---

## Caching

All API calls disk-cached in `data/04_search/.cache/<label>_<md5>.json` with a
24 h TTL. Labels: `oa_search`, `oa_doi`, `s2_refs`, `s2_cites`, `s2_recs`,
`s2_id`, `llm_score`. Re-running with the same query is free of API cost and
deterministic.

---

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | for LLM scoring | Claude Haiku 4.5 relevance scoring |
| `S2_API_KEY` | optional | Higher S2 rate limit (3 req/s vs 1 req/s) |
| `OPENALEX_EMAIL` | recommended | Polite-pool faster OpenAlex throughput |
| `UNPAYWALL_EMAIL` | required for Unpaywall | Identifier required by Unpaywall API |
| `CATALITMINE_LLM_MODEL` | optional | Override model id (default `claude-haiku-4-5`) |

---

## Worked example

```bash
# Stage A–E: discover candidates
python3 scripts/search/discover.py \
        --query "methanol to aromatics ZSM-5 Brønsted acidity" \
        --top-k 15 --depth 1

# → data/04_search/discover_methanol-to-aromatics-zsm-5-bronsted-acidity_<date>.jsonl

# Fetch OA PDFs from those candidates
python3 scripts/search/fetch_oa.py \
        --input data/04_search/discover_methanol-to-aromatics-zsm-5-bronsted-acidity_<date>.jsonl \
        --topic mta \
        --max 20

# → topics/mta/pdfs/<doi>.pdf  (only OA hits)
# → data/04_search/manual_queue_<date>.jsonl  (paywalled / unreachable)
```

---

## Open questions for v0.2

- Stage A should support multi-query expansion (synonym list) before dedupe,
  to broaden first-pass recall.
- LLM scoring prompt should be tunable per topic (MTA vs CO2→aromatic vs
  generic catalysis).
- Adding a `--feedback` flag that retrains the LLM scorer's exemplar set
  from the user's accept/reject decisions on the previous run.
