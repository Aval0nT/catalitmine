# Project Conventions — MTA / CO₂→Aromatic Text Mining

## Writing catalysis prose — MANDATORY

Before drafting any catalysis-related English text (paper sections, abstract, response to
reviewers, slide bullets, figure captions, internal memos meant to read as professional
catalysis writing), you **must first** Read `notes/catalysis_lexicon.md`.

Rules:
1. Prefer vocabulary, verbs, adjectives, and sentence templates from the lexicon.
2. Honor the **anti-patterns table** (§0). In particular: do **not** use "impaired",
   "broken (catalyst)", "good/bad" as vague descriptors, "many", "very", "things", "got",
   "nowadays", or other items in that table.
3. If a needed term is not in the lexicon, **ask the user** rather than guessing. Do not
   invent catalysis-register synonyms from general English knowledge — many of them
   (e.g. "impaired") are not used in the field.
4. After drafting, do a quick self-check pass against §0 anti-patterns.
5. Caveat: the lexicon is v1 (hand-seeded). If you encounter the same term being needed
   repeatedly, propose adding it.

This rule applies to *English* prose. Casual Chinese explanations to the user are not bound
by it, but switch to the lexicon the moment you switch to drafting English for the manuscript.

## Project plan

The active plan is `notes/project_plan_v1.md`. Main pipeline (Phases 1–5) takes priority over
branch projects (A–D). Do not promote branch work to the main pipeline without an explicit
decision from the user.

## File layout (key locations)
- `scripts/extraction/extract_docling_v2.py` — v2 evidence-extraction pipeline
- `scripts/search/semantic_scholar.py` — corpus expansion via S2
- `scripts/analysis/resolve_refs_openalex.py` — citation → DOI resolver
- `db/catalysis.db` — SQLite store
- `data/03_evidence/` — evidence_units + ref_resolved.json per paper
- `notes/` — design docs, plan, lexicon
