"""
Stage C — MatSciBERT NER Enrichment

Runs nlp-magnets/matscibert-cner (B-MAT/I-MAT token classification) over
high-value chunks and adds matbert_entities field to each record.

The NER output is written back into data/02_enriched/ alongside existing
regex enrichment fields (cde_cems, cde_quantities). Stage D (LLM extraction)
reads these fields as pre-annotated hints, reducing Pass 1 hallucination risk.

Entity types from this model:
  MAT — any material mention: metals (Zn, Ga), zeolites (ZSM-5, SAPO-34),
        substrates (methanol), products (BTX, aromatics), oxides (Al2O3)

Output fields added per chunk:
  matbert_entities  : list of {word, score, start, end}  (MAT entities only)
  matbert_mat_list  : deduplicated list of material strings (for quick LLM hint)
  matbert_version   : model ID string

Usage:
  # Single paper
  python3 scripts/extraction/ner_enrich_chunks.py --doi 10.1038_s41929-018-0078-5

  # All enriched papers
  python3 scripts/extraction/ner_enrich_chunks.py --all

  # Dry run (print entities for first chunk, no writes)
  python3 scripts/extraction/ner_enrich_chunks.py --doi ... --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

warnings.filterwarnings("ignore")

ROOT        = Path(__file__).resolve().parents[2]
ENRICHED_DIR = ROOT / "data" / "02_enriched"
PILOT_DOI   = "10.1038_s41929-018-0078-5"

NER_MODEL   = "nlp-magnets/matscibert-cner"


# ---------------------------------------------------------------------------
# Model loader (singleton)
# ---------------------------------------------------------------------------

_ner_pipeline = None


def get_pipeline():
    global _ner_pipeline
    if _ner_pipeline is None:
        from transformers import pipeline as hf_pipeline
        print(f"  Loading NER model: {NER_MODEL} ...", flush=True)
        _ner_pipeline = hf_pipeline(
            "token-classification",
            model=NER_MODEL,
            aggregation_strategy="simple",
            device=-1,  # CPU; change to 0 for CUDA GPU
        )
        print("  Model loaded.", flush=True)
    return _ner_pipeline


# ---------------------------------------------------------------------------
# NER helpers
# ---------------------------------------------------------------------------

# Tokens that are common false positives in catalysis text — keep short
# list to avoid over-filtering; we prefer recall over precision at this stage
_STOPWORDS = {
    "the", "a", "an", "of", "in", "for", "and", "or", "with", "by",
    "at", "to", "from", "via", "over", "under", "on", "per",
}


def run_ner(text: str) -> List[Dict[str, Any]]:
    """Run NER on text, return list of MAT entity dicts."""
    pipe = get_pipeline()
    try:
        raw = pipe(text)
    except Exception as exc:
        print(f"    NER error: {exc}", file=sys.stderr)
        return []

    entities = []
    for ent in raw:
        if ent["entity_group"] != "MAT":
            continue
        word = ent["word"].strip()
        # Skip very short / stopword tokens
        if len(word) < 2 or word.lower() in _STOPWORDS:
            continue
        entities.append({
            "word":  word,
            "score": round(float(ent["score"]), 4),
            "start": ent.get("start"),
            "end":   ent.get("end"),
        })
    return entities


def deduplicate_mat_list(entities: List[Dict]) -> List[str]:
    """Unique material strings, highest-score first."""
    seen: dict[str, float] = {}
    for e in entities:
        w = e["word"].lower()
        if w not in seen or e["score"] > seen[w]:
            seen[w] = e["score"]
    return sorted(seen.keys(), key=lambda w: -seen[w])


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def process_file(inp: Path, dry_run: bool = False) -> None:
    """Enrich all chunks in an enriched JSONL file with NER annotations."""
    print(f"\n→ {inp.name}", flush=True)

    chunks = [json.loads(line) for line in inp.open(encoding="utf-8")]
    enriched = []

    for i, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        text_preview = text[:60].replace("\n", " ")
        print(f"  [{i+1:02d}/{len(chunks)}] {text_preview}...")

        if dry_run:
            if i == 0:
                entities = run_ner(text)
                print(f"  [DRY RUN] entities found:")
                for e in entities:
                    print(f"    MAT  {e['score']:.3f}  '{e['word']}'")
            else:
                print("  [DRY RUN] skipping...")
            enriched.append(chunk)
            if i >= 2:
                break
            continue

        entities = run_ner(text)
        chunk["matbert_entities"] = entities
        chunk["matbert_mat_list"] = deduplicate_mat_list(entities)
        chunk["matbert_version"]  = NER_MODEL
        enriched.append(chunk)

        mat_count = len(entities)
        print(f"         → {mat_count} MAT entities: {[e['word'] for e in entities[:6]]}")

    if dry_run:
        print("\n  [DRY RUN] No writes performed.")
        return

    # Write back to same file (in-place update)
    with inp.open("w", encoding="utf-8") as f:
        for rec in enriched:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with_mat = sum(1 for c in enriched if c.get("matbert_mat_list"))
    print(f"\n  chunks enriched : {len(enriched)}")
    print(f"  chunks with MAT : {with_mat} ({with_mat/max(len(enriched),1)*100:.0f}%)")
    print(f"  written to      : {inp}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage C: MatSciBERT NER enrichment for catalyst entity recognition"
    )
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--doi", default=PILOT_DOI, help="Sanitised DOI slug")
    grp.add_argument("--all", action="store_true", help="Process all enriched files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run NER on first chunk only, no writes")
    args = parser.parse_args()

    if args.all:
        files = sorted(ENRICHED_DIR.glob("*.enriched.jsonl"))
    else:
        files = [ENRICHED_DIR / f"{args.doi}.enriched.jsonl"]

    if not files:
        print("No enriched files found.", file=sys.stderr)
        return

    for inp in files:
        if not inp.exists():
            print(f"[skip] not found: {inp}", file=sys.stderr)
            continue
        process_file(inp, dry_run=args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
