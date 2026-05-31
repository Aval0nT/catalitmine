"""
Resolve source_reference fields in evidence units to real DOIs.

Three-tier strategy per reference:
  1. PDF hyperlink annotations  — pdfplumber extracts clickable doi.org links
                                    from the reference pages. Accurate for modern
                                    papers (2010+); no network requests needed.
  2. DOI in citation text       — regex finds "10.XXXX/..." embedded in the
                                    citation string itself (some journals include it).
  3. OpenAlex title search      — fallback for old references without links.
                                    Extracts title from citation text, queries API.

Output:
  data/03_evidence/<doi_slug>.ref_resolved.json
  {
    "1": {
      "citation_text": "...",
      "doi": "10.1021/...",
      "source": "pdf_annotation" | "text_doi" | "openalex" | null,
      "oa_title": "..." | null,
      "score": 1.0 | 0.7 | ...
    },
    ...
  }

Usage:
  python3 scripts/analysis/resolve_refs_openalex.py --doi 10.1021_acscatal.1c01422
  python3 scripts/analysis/resolve_refs_openalex.py --all
  python3 scripts/analysis/resolve_refs_openalex.py --all --dry-run
  python3 scripts/analysis/resolve_refs_openalex.py --doi ... --rerun-tier3
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "data" / "03_evidence"
PDFS = ROOT / "pdfs"

OPENALEX_EMAIL = "y.piao@uu.nl"
OPENALEX_BASE  = "https://api.openalex.org/works"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def extract_ref_number(source_ref: str) -> Optional[str]:
    """Extract numeric ref ID from "Ref. [59]", "[59]", "59", etc."""
    if not source_ref:
        return None
    for pat in [r'\[(\d{1,3})\]', r'\((\d{1,3})\)',
                r'ref\.?\s*(\d{1,3})', r'^(\d{1,3})$']:
        m = re.search(pat, source_ref.strip(), re.I)
        if m:
            return m.group(1)
    return None


def _clean_doi(raw: str) -> str:
    """Normalize a raw DOI string extracted from URL or text."""
    doi = raw.strip().rstrip("/.?,;)")
    # Remove ?ref=pdf and similar query strings ACS adds
    doi = re.sub(r'\?.*$', '', doi)
    return doi


# ---------------------------------------------------------------------------
# Tier 1 — PDF hyperlink annotation extraction
# ---------------------------------------------------------------------------

def _extract_ref_dois_from_pdf(pdf_path: Path) -> Dict[str, str]:
    """
    Scan PDF pages for doi.org hyperlink annotations.
    Returns {ref_number_str: doi} by spatial matching:
      annotation Y-position → nearby text → leading [N] / N. ref number.

    Most modern papers (ACS, RSC, Elsevier, Nature, Wiley 2010+) embed
    clickable DOI links in every line of the reference section.
    """
    try:
        import pdfplumber
    except ImportError:
        return {}

    ref_dois: Dict[str, str] = {}

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                annots = page.annots or []

                # Collect DOI annotations with pdfplumber-space coords
                doi_annots = []
                for a in annots:
                    uri = a.get("uri") or ""
                    m = re.search(
                        r'https?://(?:dx\.)?doi\.org/(10\.[^\s?&#"\'\]]+)',
                        uri
                    )
                    if not m:
                        continue
                    doi = _clean_doi(m.group(1))
                    # Convert PDF bottom-left coords → pdfplumber top-of-page coords
                    top    = page.height - a["y1"]
                    bottom = page.height - a["y0"]
                    doi_annots.append({"doi": doi, "top": top, "bottom": bottom})

                if not doi_annots:
                    continue

                # Extract words with positions for this page
                words = page.extract_words(x_tolerance=3, y_tolerance=3) or []

                # Group annotation spans by DOI (same DOI = same reference entry)
                doi_to_span: Dict[str, Dict] = {}
                for ann in doi_annots:
                    d = ann["doi"]
                    if d not in doi_to_span:
                        doi_to_span[d] = {"top": ann["top"], "bottom": ann["bottom"]}
                    else:
                        doi_to_span[d]["top"]    = min(doi_to_span[d]["top"],    ann["top"])
                        doi_to_span[d]["bottom"] = max(doi_to_span[d]["bottom"], ann["bottom"])

                # For each DOI span, find the text block and extract ref number
                for doi, span in doi_to_span.items():
                    t, b = span["top"] - 4, span["bottom"] + 4
                    block = [w for w in words if w["top"] >= t and w["bottom"] <= b + 12]
                    block_text = " ".join(
                        w["text"] for w in sorted(block, key=lambda w: (w["top"], w["x0"]))
                    )

                    # Match leading ref number: [N], (N), or "N."
                    m = re.match(r'^\s*[\[\(]?(\d{1,3})[\]\)\.\s]', block_text)
                    if m:
                        ref_num = m.group(1)
                        # Don't overwrite a hit from an earlier page
                        if ref_num not in ref_dois:
                            ref_dois[ref_num] = doi

    except Exception as exc:
        print(f"    [pdf_annotation] error: {exc}")

    return ref_dois


# ---------------------------------------------------------------------------
# Tier 2 — DOI embedded in citation text
# ---------------------------------------------------------------------------

_DOI_IN_TEXT = re.compile(
    r'\b(10\.\d{4,9}/[^\s,;\]\)\"\'<>]{4,80})',
    re.I
)

def _doi_from_citation_text(citation_text: str) -> Optional[str]:
    """Find a DOI pattern directly in the citation string."""
    m = _DOI_IN_TEXT.search(citation_text)
    if m:
        return _clean_doi(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Tier 3 — OpenAlex title search (fallback)
# ---------------------------------------------------------------------------

def _extract_title(citation_text: str) -> str:
    """
    Heuristically extract the paper title from a citation string.

    Handles:
      ACS/Elsevier : "Author, A.; ... (2019). Title of paper. Journal..."
      Nature/RSC   : "Author, A. et al. Title of paper. Nat. Catal. 2018, 1."
      Springer     : "Author A et al (2018) Title of paper. J Catal 123:456"
      Numbered     : "1. Author, A. Title of paper. Journal 2010, 5, 12."
    """
    # Pattern 1: "(YEAR). Title..." — ACS/Elsevier
    m = re.search(r'\(\d{4}\)\.\s+([A-Z][^.]{15,150})', citation_text)
    if m:
        return m.group(1).strip()

    # Pattern 2: "et al. Title..." — Nature/RSC
    m = re.search(r'et al\.?\s+([A-Z][^.]{15,150})', citation_text)
    if m:
        return m.group(1).strip()

    # Pattern 3: "YEAR) Title..." — Springer
    m = re.search(r'\(\d{4}\)\s+([A-Z][^.]{15,150})', citation_text)
    if m:
        return m.group(1).strip()

    # Pattern 4: After last semicolon-author block
    m = re.search(
        r'(?:;\s*[A-Z][a-z]+,\s+[A-Z]\.(?:\s+[A-Z]\.)*\s+)'
        r'([A-Z][^.]{15,150}\.)',
        citation_text
    )
    if m:
        return m.group(1).strip()

    # Fallback: use first 150 chars (may include authors — better than nothing)
    return citation_text[:150].strip()


def _openalex_search(query: str, use_title_filter: bool = False) -> Optional[Dict]:
    """Query OpenAlex. Returns first result dict, or None."""
    if use_title_filter:
        params = urllib.parse.urlencode({
            "filter":   f"title.search:{query}",
            "per-page": "1",
            "select":   "doi,title,publication_year,authorships",
            "mailto":   OPENALEX_EMAIL,
        })
    else:
        params = urllib.parse.urlencode({
            "search":   query,
            "per-page": "1",
            "select":   "doi,title,publication_year,authorships",
            "mailto":   OPENALEX_EMAIL,
        })
    url = f"{OPENALEX_BASE}?{params}"

    for attempt in range(4):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": f"mailto:{OPENALEX_EMAIL}"}
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read())
            results = data.get("results", [])
            return results[0] if results else None
        except Exception as exc:
            msg = str(exc)
            if "429" in msg and attempt < 3:
                time.sleep(2 ** attempt * 3)
                continue
            print(f"    [OpenAlex error] {exc}")
            return None
    return None


def _score_match(citation_text: str, result: Dict) -> float:
    """Confidence 0–1: checks year + first-author surname."""
    score = 0.3
    year_m = re.search(r'(19|20)\d{2}', citation_text)
    if year_m and str(result.get("publication_year", "")) == year_m.group(0):
        score += 0.4
    authors = result.get("authorships", [])
    if authors:
        surname = (authors[0].get("author", {}).get("display_name", "") or "").split()[-1].lower()
        if surname and len(surname) > 2 and surname in citation_text.lower():
            score += 0.3
    return round(score, 2)


def _resolve_via_openalex(citation_text: str) -> Tuple[Optional[str], Optional[str], float]:
    """Return (doi, oa_title, score). Makes up to 3 API requests."""
    title_query = _extract_title(citation_text)

    result = _openalex_search(title_query, use_title_filter=True)
    if result is None:
        result = _openalex_search(title_query, use_title_filter=False)
    if result is None and len(citation_text) > 80:
        result = _openalex_search(citation_text[:150])

    if result is None:
        return None, None, 0.0

    doi   = (result.get("doi") or "").replace("https://doi.org/", "") or None
    title = result.get("title") or None
    score = _score_match(citation_text, result)

    if score < 0.4:
        return None, title, score
    return doi, title, score


# ---------------------------------------------------------------------------
# Per-paper processing
# ---------------------------------------------------------------------------

def process_doi(
    doi_slug: str,
    dry_run: bool = False,
    rerun_tier3: bool = False,
) -> Dict:
    """
    Resolve all references for one paper using the three-tier strategy.

    rerun_tier3: re-attempt OpenAlex for refs that previously got no DOI.
    """
    ref_lookup_path = EVID / f"{doi_slug}.ref_lookup.json"
    resolved_path   = EVID / f"{doi_slug}.ref_resolved.json"
    pdf_path        = PDFS / f"{doi_slug}.pdf"

    if not ref_lookup_path.exists():
        print(f"  [skip] no ref_lookup: {doi_slug}")
        return {}

    ref_lookup: Dict[str, str] = json.loads(
        ref_lookup_path.read_text(encoding="utf-8")
    )

    # Load prior results (resume support)
    resolved: Dict[str, Dict] = {}
    if resolved_path.exists():
        resolved = json.loads(resolved_path.read_text(encoding="utf-8"))

    print(f"\n→ {doi_slug}  ({len(ref_lookup)} refs, {len(resolved)} prior)")

    # ------------------------------------------------------------------
    # Tier 1: PDF annotations (batch, free)
    # ------------------------------------------------------------------
    pdf_doi_map: Dict[str, str] = {}
    if pdf_path.exists():
        print(f"  [tier-1] scanning PDF annotations…", end=" ", flush=True)
        pdf_doi_map = _extract_ref_dois_from_pdf(pdf_path)
        print(f"{len(pdf_doi_map)} DOIs extracted from PDF links")
    else:
        print(f"  [tier-1] PDF not found at {pdf_path.name}, skipping")

    # ------------------------------------------------------------------
    # Process each reference
    # ------------------------------------------------------------------
    needs_openalex: list[Tuple[str, str]] = []   # (ref_num, citation_text)

    for ref_num, citation_text in sorted(
        ref_lookup.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999
    ):
        already = resolved.get(ref_num, {})

        if dry_run:
            tier1 = f"pdf:{pdf_doi_map[ref_num]}" if ref_num in pdf_doi_map else "-"
            tier2 = f"text:{_doi_from_citation_text(citation_text)}" if _doi_from_citation_text(citation_text) else "-"
            prior = f"prior:{already.get('doi','none')}" if already else "new"
            print(f"  [{ref_num:>3}] t1={tier1}  t2={tier2}  {prior}")
            continue

        # Tier 1: PDF annotation always wins — override prior results (authoritative)
        if ref_num in pdf_doi_map:
            resolved[ref_num] = {
                "citation_text": citation_text,
                "doi":    pdf_doi_map[ref_num],
                "source": "pdf_annotation",
                "oa_title": None,
                "score":  1.0,
            }
            print(f"  [{ref_num:>3}] ✓ pdf  {pdf_doi_map[ref_num]}")
            continue

        # Tier 2: DOI in citation text?
        doi_in_text = _doi_from_citation_text(citation_text)
        if doi_in_text:
            resolved[ref_num] = {
                "citation_text": citation_text,
                "doi":    doi_in_text,
                "source": "text_doi",
                "oa_title": None,
                "score":  0.95,
            }
            print(f"  [{ref_num:>3}] ✓ text {doi_in_text}")
            continue

        # Skip tier 3 if already has a DOI (from prior run or tier 1/2 above)
        if already.get("doi"):
            continue
        # Skip tier 3 if previously attempted and --rerun-tier3 not set
        if already and not rerun_tier3:
            continue

        # Tier 3: queue for OpenAlex (rate-limited)
        needs_openalex.append((ref_num, citation_text))

    # ------------------------------------------------------------------
    # Tier 3: OpenAlex (1 req/s, only for refs not resolved above)
    # ------------------------------------------------------------------
    if needs_openalex:
        print(f"  [tier-3] OpenAlex for {len(needs_openalex)} remaining refs…")
        for ref_num, citation_text in needs_openalex:
            doi, oa_title, score = _resolve_via_openalex(citation_text)
            resolved[ref_num] = {
                "citation_text": citation_text,
                "doi":    doi,
                "source": "openalex" if doi else None,
                "oa_title": oa_title,
                "score":  score,
            }
            status = f"✓ oa   {doi}" if doi else f"✗ (score={score:.1f})"
            print(f"  [{ref_num:>3}] {citation_text[:50]:<50}  {status}")
            time.sleep(1.0)

    if dry_run:
        return resolved

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    with resolved_path.open("w", encoding="utf-8") as f:
        json.dump(resolved, f, ensure_ascii=False, indent=2)

    # Stats by tier
    tier_counts: Dict[str, int] = {}
    for v in resolved.values():
        src = v.get("source") or "unresolved"
        tier_counts[src] = tier_counts.get(src, 0) + 1

    total    = len(resolved)
    with_doi = sum(1 for v in resolved.values() if v.get("doi"))
    print(
        f"  resolved: {with_doi}/{total} ({with_doi/max(total,1)*100:.0f}%) — "
        + "  ".join(f"{k}:{n}" for k, n in sorted(tier_counts.items()))
    )
    print(f"  saved  : {resolved_path.name}")
    return resolved


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve ref numbers to DOIs (PDF annotations → text DOI → OpenAlex)"
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--doi",  help="Sanitised DOI slug (underscores)")
    grp.add_argument("--all",  action="store_true",
                     help="Process all papers with a ref_lookup file")
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--rerun-tier3",  action="store_true",
                        help="Re-attempt OpenAlex for refs that previously got no DOI")
    args = parser.parse_args()

    if args.all:
        slugs = [f.stem.replace(".ref_lookup", "")
                 for f in sorted(EVID.glob("*.ref_lookup.json"))]
    else:
        slugs = [args.doi]

    all_stats: Dict[str, Dict] = {}
    for slug in slugs:
        result = process_doi(slug, dry_run=args.dry_run,
                             rerun_tier3=args.rerun_tier3)
        if result:
            with_doi = sum(1 for v in result.values() if v.get("doi"))
            all_stats[slug] = {"total": len(result), "found": with_doi}

    print("\n=== Summary ===")
    grand_total = grand_found = 0
    for slug, s in all_stats.items():
        pct = s["found"] / max(s["total"], 1) * 100
        print(f"  {slug}: {s['found']}/{s['total']} ({pct:.0f}%)")
        grand_total += s["total"]
        grand_found += s["found"]
    if grand_total:
        print(f"\n  TOTAL: {grand_found}/{grand_total} "
              f"({grand_found/grand_total*100:.0f}% overall)")
    print("\nDone.")


if __name__ == "__main__":
    main()
