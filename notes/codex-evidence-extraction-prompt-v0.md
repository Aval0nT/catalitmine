# Codex Evidence Extraction Prompt v0

Use this prompt per high-value paragraph chunk.

## System intent
Extract **structured evidence units** from review-paper paragraphs.
Do not write a broad summary.
Do not guess missing numeric values.
If information is not stated, return null.
If one paragraph contains multiple distinct evidence units, output an array.

## Required output
Return JSON only.

## Schema
```json
{
  "evidence_id": "string",
  "source_review_doi": "string",
  "source_section": "string or null",
  "source_reference_label": ["string"],
  "authors_or_group": "string or null",
  "extraction_origin": "main_text",
  "catalyst_system": "string or null",
  "active_metal": ["string"],
  "secondary_metal": ["string"],
  "promoter": ["string"],
  "support": ["string"],
  "temperature_C": ["number"],
  "pressure_MPa": ["number"],
  "H2_CO2_ratio": ["number"],
  "main_products": ["string"],
  "conversion_text": "string or null",
  "selectivity_text": "string or null",
  "yield_text": "string or null",
  "mechanism_text": "string or null",
  "review_author_comment": "string or null",
  "pattern_value": "string or null",
  "needs_manual_check": true,
  "confidence": "low|medium|high"
}
```

## Rules
1. Prefer more, smaller evidence units over one merged unit.
2. Keep direct result statements separate from mechanism interpretations when possible.
3. Preserve reference labels like `[115]`.
4. If the review compares baseline vs promoted catalyst, split into separate evidence units.
5. Never invent support, promoter, or conditions if absent.
6. If the paragraph is too broad and not extractable, return `[]`.
