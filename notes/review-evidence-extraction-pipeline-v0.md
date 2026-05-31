# Review Evidence Extraction Pipeline v0

## Goal
Build a practical pipeline for extracting **high-granularity evidence units** from review papers, especially for CO2 hydrogenation / higher alcohol literature.

This pipeline is designed to move beyond:
- broad paper summaries
- generic review-level conclusions

and toward:
- table-row evidence extraction
- reference-level text evidence extraction
- mechanism/effect claims linked to catalyst systems
- pattern discovery and gap discovery readiness

---

# 1. Core Idea

A review paper should not be treated as a single summary object.
Instead, it should be decomposed into many **evidence units**.

An evidence unit is something like:
- one table row
- one paragraph describing a specific catalyst system
- one comparison between two systems
- one mechanism explanation tied to a specific catalyst or reference

The pipeline should extract those evidence units into a structured format.

---

# 2. Target Output

## 2.1 Main output type
A JSONL file of evidence units.

Each line should represent one extracted unit.

### Example fields
- `evidence_id`
- `source_review_doi`
- `source_review_title`
- `source_section`
- `source_reference_label`
- `source_reference_doi` (nullable)
- `extraction_origin` (`table_row` | `main_text` | `caption`)
- `catalyst_system`
- `active_metal`
- `secondary_metal`
- `promoter`
- `support`
- `temperature_C`
- `pressure_MPa`
- `H2_CO2_ratio`
- `main_products`
- `conversion`
- `selectivity`
- `yield`
- `mechanism_text`
- `review_author_comment`
- `pattern_value`
- `needs_manual_check`
- `confidence`

## 2.2 Secondary outputs
- paragraph chunk file
- table extraction intermediate files
- manual review report

---

# 3. Pipeline Architecture

## Stage A — PDF ingestion
Input:
- local review PDF

Processing:
- use `pdfplumber` to extract full text
- detect page boundaries
- retain page numbers for traceability

Output:
- `full_text.txt`
- page-indexed text blocks

### Current tool
- `pdfplumber`

---

## Stage B — Structure detection
Goal:
- segment the paper into meaningful units before LLM extraction

### Detectable structures
- section headers
- subsection headers
- table anchors (`Table 1`, `Table 2`, ...)
- figure anchors
- reference-rich paragraphs
- performance-rich paragraphs

### Heuristics
Mark a paragraph as high-value if it contains one or more of:
- reference label like `[115]`
- author phrases like `X et al.`
- action verbs: `reported`, `found`, `observed`, `showed`, `suggested`, `proposed`
- catalyst strings: `Rh/SiO2`, `CuZnFeK`, `NaCo/SiO2`, etc.
- numeric condition markers: `°C`, `MPa`, `H2/CO2`, `%`, `yield`, `selectivity`, `conversion`
- mechanism terms: `CO insertion`, `RWGS`, `formate`, `methoxy`, `carbide`, `C–C coupling`

Output:
- chunked paragraph list
- high-value paragraph candidates
- table candidate pages

---

## Stage C — Table-first extraction
Goal:
- extract structured evidence from review tables before free-text extraction

### Why table-first
Tables often contain the most compact, comparable information:
- catalyst composition
- conditions
- conversion
- selectivity
- yield
- reference labels

### v0 approach
- detect pages containing relevant tables by text anchors
- manually or semi-automatically isolate table text
- convert rows into evidence units

### Target table types
- catalyst comparison tables
- performance summary tables
- promoter/support comparison tables
- mechanism summary tables

Output:
- `table_evidence.jsonl`

---

## Stage D — LLM-assisted paragraph extraction
Goal:
- extract evidence units from high-value review paragraphs

### Why LLM is needed
Review paragraphs often encode information like:
- who did what
- on which catalyst
- with what effect
- under which conditions
- and why the authors think it happened

This is difficult to robustly extract with rigid regex/rules only.

### LLM role in v0
For each selected paragraph chunk, ask the model to:
1. identify whether it contains extractable evidence
2. output one or more normalized evidence units
3. separate factual observation from mechanism interpretation
4. preserve uncertainty
5. mark missing fields as null instead of guessing

### Important rule
The LLM must not produce free-form summaries as the main product.
It must produce structured evidence objects.

Output:
- `text_evidence.jsonl`

---

## Stage E — Merge and normalize
Goal:
- combine evidence from tables and main text
- reduce duplicates
- normalize fields

### Tasks
- deduplicate identical catalyst rows
- normalize catalyst names
- normalize promoter names
- standardize temperature/pressure formats when possible
- tag incomplete records
- attach provenance

Output:
- `review_evidence_merged.jsonl`

---

## Stage F — Manual review layer
Goal:
- allow fast human checking without re-reading everything from scratch

### Review strategy
Human does not fully redo extraction.
Instead, human checks:
- highest-value evidence units
- suspicious entries
- strong outliers
- mechanism-heavy claims
- low-confidence records

Output:
- corrected review evidence file
- notes for schema refinement

---

# 4. LLM Extraction Contract

## Input to LLM
Each request should include:
- paper metadata
- section name if known
- paragraph text or table row text
- extraction schema
- instruction to avoid guessing

## Output from LLM
Strict JSON object or JSON array.

### Required behavior
- do not invent missing numeric values
- do not merge unrelated catalyst systems into one unit
- keep evidence granular
- preserve reference labels when available
- set `needs_manual_check=true` if ambiguous

## Good unit example
A paragraph like:
> Guo et al. observed a very small amount of C2+ alcohols over CuZn, but K promotion enhanced C2+ alcohol formation.

should yield something like:
- baseline CuZn evidence unit
- K-promoted CuZn evidence unit
- mechanism/interpretation note if explicitly stated

---

# 5. Suggested File Layout

Under `/Users/avalont/Projects/knowledge/Science/`:

- `notes/review-evidence-extraction-pipeline-v0.md`
- `data/review_chunks/`
- `data/review_tables/`
- `data/review_evidence/`
- `scripts/review_extraction/`

### Expected files
- `data/review_chunks/<doi>.chunks.jsonl`
- `data/review_tables/<doi>.tables.jsonl`
- `data/review_evidence/<doi>.table_evidence.jsonl`
- `data/review_evidence/<doi>.text_evidence.jsonl`
- `data/review_evidence/<doi>.merged.jsonl`

---

# 6. Codex / Model Usage Strategy

## Can Codex be used as the extraction engine?
Yes — for v0, Codex can be used as the extraction model, especially for:
- paragraph understanding
- schema filling
- claim splitting
- mechanism/evidence separation

## Best use pattern
Do not send the whole paper at once.
Instead:
- chunk first
- filter to high-value chunks
- send chunk-by-chunk
- require structured output

## Why this matters
This improves:
- extraction fidelity
- reproducibility
- cost control
- manual review traceability

---

# 7. v0 Scope

The first working version should NOT try to solve everything.

## v0 should do:
- full-text extraction from PDF using `pdfplumber`
- high-value paragraph detection
- manual or semi-manual table row extraction for one review
- LLM extraction for high-value paragraph chunks
- merged JSONL evidence output

## v0 should NOT try to do yet:
- perfect table structure recovery for all tables
- full citation-to-DOI resolution for every reference
- multi-paper global deduplication
- complete automatic unit normalization
- complete contradiction graphing

---

# 8. Testing Plan

## First test paper
- `10.1016/j.apcatb.2021.120073`

## Test goals
1. extract all major table rows from one catalyst-family table
2. extract 10–20 high-value paragraph evidence units
3. compare table-derived vs paragraph-derived evidence
4. estimate realistic evidence yield from one review

## Success criteria
- output is no longer broad/fuzzy summary
- evidence units are catalyst/reference-level
- manual review can verify entries quickly
- at least some patterns become visible from merged evidence

---

# 9. Expected Benefits

If this pipeline works, later it should support:
- scaling from 1 review to many reviews
- accumulation of evidence units across papers
- pattern discovery
- gap discovery
- identification of underexplored metal/promoter/support/mechanism combinations

This is the correct bridge from:
- review reading
- to structured evidence
- to future self-supervised / semi-self-supervised research-space mining

---

# 10. Immediate Next Build Step

Build `v0` in this order:
1. chunk generator
2. high-value paragraph detector
3. JSON schema for evidence units
4. Codex prompt template for chunk extraction
5. first end-to-end test on `10.1016/j.apcatb.2021.120073`
