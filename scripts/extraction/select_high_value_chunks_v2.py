"""
Stage B v2 — High-value chunk selection with section-aware filtering.

For primary papers (--paper-type primary):
  - Abstract:     always kept (contains key numbers and scope)
  - Introduction: dropped entirely (literature-citation noise)
  - Methods/Experimental: kept (reaction conditions T, P, WHSV)
  - Results/Discussion:   kept (core data)
  - Conclusion:   kept
  - References/Acknowledgements: dropped

For reviews (--paper-type review):
  - Behaves identically to v1 (no section filtering)

Old script select_high_value_chunks.py is NOT modified — use it as fallback.

Usage:
  python3 scripts/extraction/select_high_value_chunks_v2.py --doi 10.1016_j.jcat.2018.03.032 --paper-type primary
  python3 scripts/extraction/select_high_value_chunks_v2.py --all --paper-type primary
  python3 scripts/extraction/select_high_value_chunks_v2.py --all --paper-type review
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[2]
CHUNKS_DIR = ROOT / "data" / "01_chunks"

# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

# Section name alternatives (shared by both patterns below)
_SECTION_NAMES = (
    r"abstract|introduction|"
    r"experimental(?:\s+section)?|"
    r"materials?\s+and\s+methods?|methods?\s+and\s+materials?|"
    r"methods?|materials?|synthesis|catalyst\s+preparation|"
    r"results?(?:\s+and\s+discussion)?|"
    r"discussion|conclusions?|"
    r"acknowledgem\w*|references?|"
    r"supporting\s+information|appendix"
)

# Match at the very START of a chunk
_SECTION_START_RE = re.compile(
    r"^\s*(?:\d[\d.]*\.?\s+)?(" + _SECTION_NAMES + r")", re.I
)

# Match after a sentence end / newline — catches headers mid-chunk or carried
# over from prior chunk (e.g. "...pathway. 2. Experimental\nContent...")
_SECTION_INLINE_RE = re.compile(
    r"(?:^|[.\n]\s{0,4})(?:\d[\d.]*\.?\s+)?(" + _SECTION_NAMES + r")\b",
    re.I | re.MULTILINE,
)

# Sections whose chunks are DROPPED for primary papers
_INTRO_LABELS = {"introduction"}
_TAIL_LABELS  = {"acknowledgements", "acknowledgments", "references",
                 "supporting information", "appendix"}

# Sections always kept regardless of high_value score
_KEEP_ALWAYS_LABELS = {"abstract"}

# Sections that should OVERRIDE the high_value score filter (always include all chunks)
_HIGH_PRIORITY_LABELS = {
    "abstract",
    "experimental", "experimental section",
    "materials and methods", "methods and materials", "methods",
    "synthesis", "catalyst preparation",
}


def _parse_section(text: str) -> str | None:
    """
    Return normalised section name if a header is detected, else None.
    Checks: (1) start of chunk, (2) inline after sentence/newline.
    """
    # 1. Strict: header at start of chunk
    m = _SECTION_START_RE.match(text)
    if m:
        return m.group(1).lower().strip()
    # 2. Lenient: header appears after a sentence end or newline within first 300 chars
    # (catches "...previous sentence. 2. Experimental\nContent...")
    m = _SECTION_INLINE_RE.search(text[:300])
    if m:
        return m.group(1).lower().strip()
    return None


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_file(inp: Path, paper_type: str, force: bool = False) -> None:
    doi_slug = inp.stem.replace(".chunks", "")
    out = CHUNKS_DIR / f"{doi_slug}.high_value_chunks.jsonl"

    if out.exists() and not force:
        print(f"  [skip] already selected: {out.name}")
        return

    chunks = [json.loads(line) for line in inp.open(encoding="utf-8")]

    if paper_type != "primary":
        # Review / unknown: identical to v1
        selected = [c for c in chunks if c.get("is_high_value")]
        selected.sort(key=lambda c: (-c.get("high_value_score", 0), c.get("page", 0)))
        _write(out, selected, len(chunks), mode="review-passthrough")
        return

    # ── Primary paper: section-aware filtering ────────────────────────────
    # Sort by page order for state-machine traversal
    ordered = sorted(chunks, key=lambda c: (c.get("page", 0), c.get("chunk_index", 0)))

    current_section: str = "preamble"   # before Abstract
    selected: list[dict] = []
    dropped_intro = 0
    dropped_tail  = 0

    for chunk in ordered:
        text = chunk.get("text", "")
        is_hv = chunk.get("is_high_value", False)
        score = chunk.get("high_value_score", 0)

        # Detect section transition
        detected = _parse_section(text)
        if detected:
            current_section = detected

        section_norm = current_section.lower()

        # Drop Introduction entirely
        if section_norm in _INTRO_LABELS:
            dropped_intro += 1
            continue

        # Drop tail sections (refs, ack, appendix)
        if section_norm in _TAIL_LABELS:
            dropped_tail += 1
            continue

        # Abstract & methods: keep even if score is low
        if section_norm in _HIGH_PRIORITY_LABELS:
            selected.append(chunk)
            continue

        # All other sections: respect high_value filter
        if is_hv:
            selected.append(chunk)

    # Safety: if too few chunks remain (e.g. Perspective/Review with no Methods section),
    # fall back to v1 behaviour to avoid losing all content.
    hv_original = sum(1 for c in chunks if c.get("is_high_value"))
    min_keep = max(8, int(hv_original * 0.25))
    if len(selected) < min_keep and hv_original > 0:
        print(f"  [fallback→v1] only {len(selected)} chunks after intro-drop "
              f"(need ≥{min_keep}), reverting to full high-value set")
        selected = [c for c in chunks if c.get("is_high_value")]
        dropped_intro = dropped_tail = 0

    _write(out, selected, len(chunks), mode="primary-filtered",
           dropped_intro=dropped_intro, dropped_tail=dropped_tail)


def _write(out: Path, selected: list[dict], total: int,
           mode: str = "", dropped_intro: int = 0, dropped_tail: int = 0) -> None:
    with out.open("w", encoding="utf-8") as f:
        for c in selected:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    suffix = ""
    if mode == "primary-filtered":
        suffix = f"  (intro dropped: {dropped_intro}, tail dropped: {dropped_tail})"
    print(f"  → {len(selected)}/{total} chunks kept{suffix}  →  {out.name}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage B v2: section-aware high-value chunk selection"
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--doi",  help="Sanitised DOI slug (underscores)")
    grp.add_argument("--all",  action="store_true")
    parser.add_argument(
        "--paper-type", choices=["primary", "review"], default="primary",
        help="primary = skip Introduction; review = v1 passthrough (default: primary)"
    )
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing .high_value_chunks.jsonl")
    args = parser.parse_args()

    if args.all:
        files = sorted(CHUNKS_DIR.glob("*.chunks.jsonl"))
    else:
        files = [CHUNKS_DIR / f"{args.doi}.chunks.jsonl"]

    for f in files:
        if not f.exists():
            print(f"[skip] not found: {f}", file=sys.stderr)
            continue
        process_file(f, paper_type=args.paper_type, force=args.force)


if __name__ == "__main__":
    main()
