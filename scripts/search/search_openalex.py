#!/usr/bin/env python3
"""
search_openalex.py — Literature search via OpenAlex + Unpaywall OA check

Usage:
  python3 scripts/search/search_openalex.py --query "methanol to aromatics zeolite" --min-citations 30
  python3 scripts/search/search_openalex.py --query "CO2 hydrogenation aromatics bifunctional" --min-year 2018 --min-if-tier A
  python3 scripts/search/search_openalex.py --query "MTA HZSM-5 selectivity" --min-citations 20 --max-results 50

Output:
  data/04_search/<sanitized_query>_<date>.csv

Required:
  pip install requests
"""

import argparse
import csv
import json
import time
import re
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:
    raise SystemExit("Install requests first: pip install requests")

# parents[2]: this file lives in scripts/search/, two levels below the repo
# root — parents[1] wrote output into scripts/data/, which is NOT gitignored
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "04_search"   # gitignored (copyrighted abstracts)

# ---------------------------------------------------------------------------
# Journal IF table — approximate 2023/2024 values, edit as needed
# Tier S: IF > 15 | Tier A: IF 8–15 | Tier B: IF 4–8 | Tier C: IF 2–4
# ---------------------------------------------------------------------------
JOURNAL_IF: dict[str, tuple[str, float]] = {
    # Tier S
    "Nature Catalysis":                                 ("S", 42.0),
    "Nature Energy":                                    ("S", 60.0),
    "Energy & Environmental Science":                   ("S", 32.0),
    "Joule":                                            ("S", 39.0),
    "ACS Energy Letters":                               ("S", 19.0),
    "Angewandte Chemie International Edition":          ("S", 16.1),
    "Angewandte Chemie":                                ("S", 16.1),
    "Journal of the American Chemical Society":         ("S", 15.0),
    # Tier A
    "Applied Catalysis B: Environmental":               ("A", 22.1),
    "Applied Catalysis B: Environment and Energy":      ("A", 22.1),
    "Chemical Engineering Journal":                     ("A", 15.1),
    "ACS Catalysis":                                    ("A", 12.9),
    "Advanced Functional Materials":                    ("A", 18.5),
    "Advanced Energy Materials":                        ("A", 27.8),
    "Chemical Science":                                 ("A",  9.0),
    "ChemSusChem":                                      ("A",  8.1),
    "Green Chemistry":                                  ("A",  9.8),
    "Nano Energy":                                      ("A", 17.6),
    # Tier B
    "Journal of Catalysis":                             ("B",  6.9),
    "Applied Catalysis A: General":                     ("B",  5.4),
    "Catalysis Today":                                  ("B",  5.9),
    "ChemCatChem":                                      ("B",  5.0),
    "Catalysis Science & Technology":                   ("B",  5.0),
    "Fuel":                                             ("B",  7.0),
    "Industrial & Engineering Chemistry Research":      ("B",  4.2),
    "Microporous and Mesoporous Materials":             ("B",  4.8),
    "Fuel Processing Technology":                       ("B",  5.8),
    "Molecular Catalysis":                              ("B",  4.0),
    "Journal of CO2 Utilization":                       ("B",  7.1),
    "International Journal of Hydrogen Energy":         ("B",  7.2),
    # Tier C
    "Catalysis Communications":                         ("C",  3.5),
    "Reaction Chemistry & Engineering":                 ("C",  4.0),
    "Chinese Journal of Catalysis":                     ("C",  6.7),
    "Journal of Energy Chemistry":                      ("C", 13.1),  # upgraded, was lower
    "New Journal of Chemistry":                         ("C",  3.1),
    "RSC Advances":                                     ("C",  3.9),
}

TIER_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3, "?": 4}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def openalex_search(query: str, min_year: int, min_citations: int,
                    max_results: int, email: str) -> list[dict]:
    """Query OpenAlex works endpoint and return raw results."""
    base = "https://api.openalex.org/works"
    headers = {"User-Agent": f"CatalysisMiner/1.0 (mailto:{email})"}
    results = []
    per_page = min(max_results, 50)
    page = 1

    filters = [
        f"publication_year:>{min_year - 1}",
        f"cited_by_count:>{min_citations - 1}",
        "type:article",
    ]

    while len(results) < max_results:
        params = {
            "search": query,
            "filter": ",".join(filters),
            "per-page": per_page,
            "page": page,
            "select": "id,doi,title,publication_year,cited_by_count,"
                      "primary_location,open_access,abstract_inverted_index",
        }
        resp = requests.get(base, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("results", [])
        if not items:
            break
        results.extend(items)
        if len(results) >= data["meta"]["count"] or len(items) < per_page:
            break
        page += 1
        time.sleep(0.2)  # polite pool rate limit

    return results[:max_results]


def decode_abstract(inverted: "dict | None") -> str:
    """OpenAlex stores abstracts as inverted index {word: [positions]}."""
    if not inverted:
        return ""
    words = [""] * (max(max(v) for v in inverted.values()) + 1)
    for word, positions in inverted.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words)


def get_journal_name(work: dict) -> str:
    try:
        return work["primary_location"]["source"]["display_name"] or ""
    except (KeyError, TypeError):
        return ""


def get_if_tier(journal: str) -> "tuple[str, float]":
    """Look up IF tier, try partial match if exact fails.

    Journal-less works return '?': the old two-way substring test made the
    empty string match every key, handing Tier S to any work with no journal
    (and 'Science' to 'Chemical Science')."""
    if not journal:
        return ("?", 0.0)
    if journal in JOURNAL_IF:
        return JOURNAL_IF[journal]
    jl = journal.lower()
    # short flagship names need EXACT matching: as substring keys they would
    # swallow longer distinct journals ("Chem" → "Chemical Engineering Journal")
    short_exact = {"nature": ("S", 50.0), "science": ("S", 45.0),
                   "chem": ("S", 19.0)}
    if jl in short_exact:
        return short_exact[jl]
    # one-directional: a known KEY contained in the (longer) reported name,
    # e.g. "Applied Catalysis B: Environmental (incl. Energy)" — never the
    # reverse, which let short names swallow longer distinct journals
    for k, v in JOURNAL_IF.items():
        if k.lower() in jl:
            return v
    return ("?", 0.0)


def check_unpaywall(doi: str, email: str) -> "tuple[bool, str]":
    """Return (is_oa, pdf_url_or_empty)."""
    if not doi:
        return False, ""
    clean_doi = doi.replace("https://doi.org/", "").strip()
    url = f"https://api.unpaywall.org/v2/{clean_doi}?email={email}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 404:
            return False, ""
        resp.raise_for_status()
        data = resp.json()
        is_oa = data.get("is_oa", False)
        pdf_url = ""
        best = data.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf") or best.get("url") or ""
        return is_oa, pdf_url
    except Exception:
        return False, ""


def sanitize(s: str) -> str:
    return re.sub(r"[^\w\-]", "_", s)[:60]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Search catalysis literature via OpenAlex")
    parser.add_argument("--query", required=True, help="Search query, e.g. 'methanol to aromatics zeolite'")
    parser.add_argument("--min-citations", type=int, default=20, help="Minimum citation count (default: 20)")
    parser.add_argument("--min-year", type=int, default=2015, help="Minimum publication year (default: 2015)")
    parser.add_argument("--min-if-tier", choices=["S", "A", "B", "C", "?"], default="B",
                        help="Minimum IF tier: S>A>B>C (default: B, i.e. IF≥4)")
    parser.add_argument("--max-results", type=int, default=100, help="Max results from OpenAlex (default: 100)")
    parser.add_argument("--email", default="researcher@uu.nl",
                        help="Your email for API polite pool (default: researcher@uu.nl)")
    parser.add_argument("--no-unpaywall", action="store_true", help="Skip Unpaywall OA check (faster)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)   # not at import time
    min_tier_rank = TIER_ORDER[args.min_if_tier]

    print(f"\nSearch query: {args.query}")
    print(f"Filters: citations≥{args.min_citations} | year≥{args.min_year} | IF tier≥{args.min_if_tier}")
    print("Querying OpenAlex...")

    raw = openalex_search(
        query=args.query,
        min_year=args.min_year,
        min_citations=args.min_citations,
        max_results=args.max_results,
        email=args.email,
    )
    print(f"  OpenAlex returned {len(raw)} results; starting IF filter + OA check...")

    rows = []
    for i, work in enumerate(raw):
        journal = get_journal_name(work)
        tier, if_val = get_if_tier(journal)

        # IF tier filter
        if TIER_ORDER.get(tier, 4) > min_tier_rank:
            continue

        doi = (work.get("doi") or "").replace("https://doi.org/", "")
        title = work.get("title") or ""
        year = work.get("publication_year") or ""
        citations = work.get("cited_by_count") or 0
        abstract = decode_abstract(work.get("abstract_inverted_index"))

        # OA check
        is_oa, pdf_url = False, ""
        if not args.no_unpaywall and doi:
            is_oa, pdf_url = check_unpaywall(doi, args.email)
            if (i + 1) % 10 == 0:
                print(f"  processed {i+1}/{len(raw)} ...")
            time.sleep(0.1)

        rows.append({
            "doi": doi,
            "title": title,
            "year": year,
            "citations": citations,
            "journal": journal,
            "if_tier": tier,
            "if_approx": if_val,
            "is_oa": is_oa,
            "pdf_url": pdf_url,
            "abstract_snippet": abstract[:300].replace("\n", " "),
        })

    # Sort by citations descending
    rows.sort(key=lambda r: -r["citations"])

    # Output
    out_name = f"{sanitize(args.query)}_{date.today().isoformat()}.csv"
    out_path = OUT_DIR / out_name

    fieldnames = ["doi", "title", "year", "citations", "journal",
                  "if_tier", "if_approx", "is_oa", "pdf_url", "abstract_snippet"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    oa_count = sum(1 for r in rows if r["is_oa"])
    print(f"\nDone — {len(rows)} papers after filtering")
    print(f"  with OA full text: {oa_count} (directly downloadable)")
    print(f"  results saved to: {out_path}")

    # Print top 10 preview
    print(f"\nTop 10 preview (sorted by citations):")
    print(f"{'#':<3} {'Year':<6} {'Cites':<6} {'IFtier':<6} {'Journal':<35} {'Title'}")
    print("-" * 120)
    for i, r in enumerate(rows[:10]):
        oa_mark = "✓OA" if r["is_oa"] else "   "
        journal_short = r["journal"][:33] + ".." if len(r["journal"]) > 35 else r["journal"]
        title_short = r["title"][:60] + "..." if len(r["title"]) > 60 else r["title"]
        print(f"{i+1:<3} {r['year']:<6} {r['citations']:<6} {r['if_tier']:<6} {journal_short:<35} {oa_mark} {title_short}")


if __name__ == "__main__":
    main()
