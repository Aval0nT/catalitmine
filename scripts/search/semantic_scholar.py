"""
Semantic Scholar API integration for corpus expansion.

Capabilities used:
  - /paper/{id}            — fetch metadata + references + citations for a known DOI
  - /paper/search          — keyword search to find new candidates
  - /recommendations/v1/   — "more like these" recommendations from seed papers
  - /graph/v1/paper/{id}/citations  — retrieve papers that cite a given paper
  - /graph/v1/paper/{id}/references — retrieve papers cited by a given paper

Rate limit: 1 req/s.  Script enforces this automatically.

Usage:
  # Expand corpus from all papers already in DB:
  python3 scripts/search/semantic_scholar.py --mode expand --out data/04_search/s2_candidates.jsonl

  # Find citing papers for a single DOI:
  python3 scripts/search/semantic_scholar.py --mode citations --doi 10.1021/acscatal.5b00192

  # Keyword search:
  python3 scripts/search/semantic_scholar.py --mode search --query "methanol to aromatics ZSM-5"
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ── Bootstrap ─────────────────────────────────────────────────────────────────

def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()

S2_API_KEY = os.environ.get("S2_API_KEY", "")
BASE = "https://api.semanticscholar.org/graph/v1"
HEADERS = {"x-api-key": S2_API_KEY} if S2_API_KEY else {}

DB = ROOT / "db" / "catalysis.db"

# ── Rate limiter ──────────────────────────────────────────────────────────────

_last_call: float = 0.0

def _get(url: str, params: dict | None = None) -> dict:
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 1.05:           # 1 req/s with small buffer
        time.sleep(1.05 - elapsed)

    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            _last_call = time.time()
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} for {url}: {body[:200]}") from e


# ── Field sets ────────────────────────────────────────────────────────────────

PAPER_FIELDS = "paperId,externalIds,title,abstract,year,authors,journal,citationCount,influentialCitationCount,isOpenAccess,openAccessPdf"

# ── Core API calls ────────────────────────────────────────────────────────────

def fetch_paper(doi: str) -> dict:
    """Fetch metadata for a single paper by DOI."""
    url = f"{BASE}/paper/DOI:{urllib.parse.quote(doi, safe='')}"
    return _get(url, {"fields": PAPER_FIELDS})


def fetch_citations(doi: str, limit: int = 100) -> list[dict]:
    """Papers that cite this DOI."""
    url = f"{BASE}/paper/DOI:{urllib.parse.quote(doi, safe='')}/citations"
    data = _get(url, {"fields": PAPER_FIELDS, "limit": limit})
    return [item["citingPaper"] for item in data.get("data", [])]


def fetch_references(doi: str, limit: int = 100) -> list[dict]:
    """Papers referenced by this DOI."""
    url = f"{BASE}/paper/DOI:{urllib.parse.quote(doi, safe='')}/references"
    data = _get(url, {"fields": PAPER_FIELDS, "limit": limit})
    return [item["citedPaper"] for item in data.get("data", [])]


def search_papers(query: str, limit: int = 20) -> list[dict]:
    """Full-text keyword search."""
    data = _get(
        f"{BASE}/paper/search",
        {"query": query, "fields": PAPER_FIELDS, "limit": limit},
    )
    return data.get("data", [])


def fetch_recommendations(seed_dois: list[str], limit: int = 20) -> list[dict]:
    """Get recommended papers similar to a set of seed papers."""
    # Resolve DOIs → S2 paperIds first
    seed_ids = []
    for doi in seed_dois:
        try:
            p = fetch_paper(doi)
            if p.get("paperId"):
                seed_ids.append(p["paperId"])
        except Exception as e:
            print(f"  ⚠ could not resolve {doi}: {e}")

    if not seed_ids:
        return []

    url = "https://api.semanticscholar.org/recommendations/v1/papers"
    payload = json.dumps({"positivePaperIds": seed_ids}).encode()
    req = urllib.request.Request(
        url + f"?fields={PAPER_FIELDS}&limit={limit}",
        data=payload,
        headers={**HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 1.05:
        time.sleep(1.05 - elapsed)
    with urllib.request.urlopen(req, timeout=30) as r:
        _last_call = time.time()
        return json.loads(r.read()).get("recommendedPapers", [])


# ── Helpers ───────────────────────────────────────────────────────────────────

def paper_to_row(p: dict) -> dict:
    """Normalise S2 paper dict to a flat candidate row."""
    doi = (p.get("externalIds") or {}).get("DOI", "")
    authors = p.get("authors") or []
    first_author = authors[0].get("name", "?").split()[-1] if authors else "?"
    journal = ""
    if p.get("journal"):
        journal = p["journal"].get("name", "") or ""
    return {
        "doi":          doi,
        "title":        p.get("title", ""),
        "first_author": first_author,
        "year":         p.get("year"),
        "journal":      journal,
        "abstract":     (p.get("abstract") or "")[:800],
        "citations":    p.get("citationCount", 0),
        "influential":  p.get("influentialCitationCount", 0),
        "open_access":  p.get("isOpenAccess", False),
        "pdf_url":      (p.get("openAccessPdf") or {}).get("url", ""),
        "s2_id":        p.get("paperId", ""),
    }


def load_known_dois() -> set[str]:
    """DOIs already in our DB."""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT doi FROM papers")
    known = {r[0].lower().strip() for r in cur.fetchall()}
    conn.close()
    return known


def deduplicate(candidates: list[dict], known: set[str]) -> list[dict]:
    seen = set()
    out = []
    for c in candidates:
        doi = (c.get("doi") or "").lower().strip()
        if not doi:
            continue
        if doi in known or doi in seen:
            continue
        seen.add(doi)
        out.append(c)
    return out


# ── Modes ─────────────────────────────────────────────────────────────────────

def mode_expand(out_path: Path) -> None:
    """Fetch citations + recommendations for all papers in DB."""
    known = load_known_dois()
    print(f"Known DOIs in DB: {len(known)}")

    all_candidates: list[dict] = []
    dois = sorted(known)

    # 1. Citations of each paper
    print("\n── Citation sweep ──")
    for doi in dois:
        print(f"  {doi} …", end=" ", flush=True)
        try:
            citing = fetch_citations(doi, limit=50)
            new = [paper_to_row(p) for p in citing if p.get("externalIds")]
            print(f"{len(new)} citing papers")
            all_candidates.extend(new)
        except Exception as e:
            print(f"error: {e}")

    # 2. Recommendations from MTA seed papers (high-priority subset)
    print("\n── Recommendations from MTA seed papers ──")
    mta_dois = [d for d in dois if "acscatal" in d or "iecr" in d or "c9ra" in d]
    try:
        recs = fetch_recommendations(mta_dois[:5], limit=30)
        new = [paper_to_row(p) for p in recs if p.get("externalIds")]
        print(f"  {len(new)} recommendations")
        all_candidates.extend(new)
    except Exception as e:
        print(f"  Recommendation error: {e}")

    # 3. Deduplicate and filter
    novel = deduplicate(all_candidates, known)
    # Sort by influential citation count descending
    novel.sort(key=lambda x: x.get("influential", 0), reverse=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for row in novel:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\n✓ {len(novel)} novel candidates → {out_path}")
    print("\nTop 20 by influential citations:")
    for r in novel[:20]:
        print(f"  [{r['influential']:3d} inf] {r['first_author']} {r['year']}  {r['doi']}")
        print(f"         {r['title'][:80]}")


def mode_citations(doi: str) -> None:
    """Print citing papers for a single DOI."""
    print(f"Citing papers for {doi}:")
    papers = fetch_citations(doi)
    papers.sort(key=lambda p: p.get("influentialCitationCount", 0) or 0, reverse=True)
    for p in papers:
        r = paper_to_row(p)
        print(f"  [{r['influential']:3d} inf / {r['citations']:4d} cit]  "
              f"{r['first_author']} {r['year']}  {r['doi'] or r['s2_id']}")
        print(f"    {r['title'][:80]}")


def mode_search(query: str, limit: int = 20) -> None:
    """Keyword search."""
    print(f"Search: '{query}'")
    papers = search_papers(query, limit=limit)
    for p in papers:
        r = paper_to_row(p)
        oa = "🔓" if r["open_access"] else "  "
        print(f"  {oa} {r['first_author']} {r['year']}  {r['doi'] or r['s2_id']}")
        print(f"     {r['title'][:80]}")
        if r["abstract"]:
            print(f"     {r['abstract'][:120]}…")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Semantic Scholar corpus expansion")
    ap.add_argument("--mode", choices=["expand", "citations", "search", "recommendations"],
                    default="expand")
    ap.add_argument("--doi",   help="DOI for citations/references mode")
    ap.add_argument("--query", help="Search query")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out",   default=str(ROOT / "data/04_search/s2_candidates.jsonl"))
    args = ap.parse_args()

    if args.mode == "expand":
        mode_expand(Path(args.out))
    elif args.mode == "citations":
        if not args.doi:
            ap.error("--doi required for citations mode")
        mode_citations(args.doi)
    elif args.mode == "search":
        if not args.query:
            ap.error("--query required for search mode")
        mode_search(args.query, args.limit)
    elif args.mode == "recommendations":
        known = load_known_dois()
        recs = fetch_recommendations(list(known)[:5], limit=args.limit)
        for p in recs:
            r = paper_to_row(p)
            print(f"  {r['first_author']} {r['year']}  {r['doi']}")
            print(f"    {r['title'][:80]}")


if __name__ == "__main__":
    main()
