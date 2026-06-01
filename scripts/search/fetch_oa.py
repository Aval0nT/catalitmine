"""
fetch_oa.py — Open-Access paper fetcher (Phase 0 default backend).

Resolves PDF URLs from open sources only — never bypasses publisher paywalls.

Sources (probed in priority order):
  1. OpenAlex `oa_url` (already attached to the Candidate by discover.py)
  2. Unpaywall                     — needs UNPAYWALL_EMAIL in .env
  3. arXiv API                     — preprint match by title (or DOI)
  4. ChemRxiv API                  — preprint match by title

Paywalled-only papers → FetchResult(success=False, source="skip:not_oa")
and are appended to data/04_search/manual_queue_<date>.jsonl so an
InstitutionalFetcher (paper-fetcher-mcp plug-in) can pick them up later.

CLI:
  python3 scripts/search/fetch_oa.py \
        --input data/04_search/discover_<slug>_<date>.jsonl \
        --topic mta \
        [--max N] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Optional

# Local imports — keep the script runnable from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetcher import (Candidate, FetchResult, PaperFetcher,  # noqa: E402
                     sanitize_doi, doi_to_filename)

ROOT = Path(__file__).resolve().parents[2]

# ── env ───────────────────────────────────────────────────────────────────────

def _load_env() -> None:
    """A .env value fills in any variable that is unset OR present but empty
    (so an exported empty var does not shadow a real key in .env)."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if not os.environ.get(k, "").strip():
                    os.environ[k] = v

_load_env()

UNPAYWALL_EMAIL = (os.environ.get("UNPAYWALL_EMAIL")
                   or os.environ.get("USER_EMAIL")
                   or "").strip()
USER_AGENT      = "catalitmine/0.1 (https://github.com/Aval0nT/catalitmine)"

# ── polite HTTP ───────────────────────────────────────────────────────────────

_last: float = 0.0

def _polite_get(url: str, *, headers: dict | None = None,
                min_interval: float = 1.0, timeout: int = 30) -> bytes:
    global _last
    wait = min_interval - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(
        url,
        headers={**(headers or {}), "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        _last = time.time()
        return r.read()


def _download_pdf(url: str, dest: Path, *, timeout: int = 60) -> bool:
    """Download a URL; only write if the body looks like a PDF."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = r.read()
    except Exception:
        return False
    if not content.startswith(b"%PDF"):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return True


# ── individual source resolvers ───────────────────────────────────────────────

def _from_openalex_oa_url(c: Candidate) -> Optional[str]:
    return c.oa_url or None


def _from_unpaywall(doi: str) -> Optional[str]:
    if not UNPAYWALL_EMAIL:
        return None
    url = (f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi, safe='')}"
           f"?email={urllib.parse.quote(UNPAYWALL_EMAIL)}")
    try:
        data = json.loads(_polite_get(url))
    except Exception:
        return None
    best = data.get("best_oa_location") or {}
    return best.get("url_for_pdf") or None


_ARXIV_ID_RE = re.compile(r'<id>https?://arxiv\.org/abs/([^<]+)</id>')

def _from_arxiv(title: str, doi: str) -> Optional[str]:
    """Match an arXiv preprint by exact-ish title.

    arXiv API uses Lucene syntax; we wrap the title in `ti:"…"` so it must
    appear (approximately) in the title field. Only the first hit is used.
    """
    if not title:
        return None
    q = urllib.parse.urlencode({
        "search_query": f'ti:"{title[:140]}"',
        "max_results":  "3",
    })
    url = f"https://export.arxiv.org/api/query?{q}"
    try:
        xml = _polite_get(url, min_interval=3.0).decode("utf-8", errors="replace")
    except Exception:
        return None
    m = _ARXIV_ID_RE.search(xml)
    if not m:
        return None
    return f"https://arxiv.org/pdf/{m.group(1)}.pdf"


def _from_chemrxiv(title: str) -> Optional[str]:
    if not title:
        return None
    url = ("https://chemrxiv.org/engage/api-gateway/chemrxiv/public/v1/items"
           f"?term={urllib.parse.quote(title[:120])}&limit=3")
    try:
        data = json.loads(_polite_get(url))
    except Exception:
        return None
    hits = data.get("itemHits") or []
    if not hits:
        return None
    asset = ((hits[0].get("item") or {}).get("asset") or {})
    return (asset.get("original") or {}).get("url") or None


# ── Default fetcher ───────────────────────────────────────────────────────────

class OAFetcher:
    name = "oa"

    DEFAULT_SOURCES = ("openalex", "unpaywall", "arxiv", "chemrxiv")

    def __init__(self, sources: tuple[str, ...] = DEFAULT_SOURCES):
        self.sources = sources

    # PaperFetcher protocol -------------------------------------------------

    def can_fetch(self, c: Candidate) -> bool:
        return bool(sanitize_doi(c.doi))

    def fetch(self, c: Candidate, dest_dir: Path) -> FetchResult:
        doi = sanitize_doi(c.doi)
        if not doi:
            return FetchResult(c, success=False, source="skip:no_doi",
                               error="empty DOI")
        out = dest_dir / doi_to_filename(doi)
        if out.exists():
            return FetchResult(c, success=True, pdf_path=out,
                               source="cache:already_exists")

        for src in self.sources:
            url = self.resolve_url(src, c)
            if not url:
                continue
            if _download_pdf(url, out):
                return FetchResult(c, success=True, pdf_path=out, source=src)
        return FetchResult(c, success=False, source="skip:not_oa",
                           error="no OA URL found across sources")

    # Internal -------------------------------------------------------------

    def resolve_url(self, src: str, c: Candidate) -> Optional[str]:
        if src == "openalex":  return _from_openalex_oa_url(c)
        if src == "unpaywall": return _from_unpaywall(sanitize_doi(c.doi))
        if src == "arxiv":     return _from_arxiv(c.title or "", c.doi)
        if src == "chemrxiv":  return _from_chemrxiv(c.title or "")
        return None


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 0: Open-Access paper fetcher")
    ap.add_argument("--input",   required=True,
                    help="Input discover_*.jsonl produced by discover.py")
    ap.add_argument("--topic",   required=True,
                    choices=("mta", "co2a", "shared"),
                    help="Destination topic folder under topics/<topic>/pdfs/")
    ap.add_argument("--max",     type=int, default=None,
                    help="Stop after fetching N PDFs (excluding cache hits)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Probe OA URLs only; do not download")
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        raise SystemExit(f"Input file not found: {in_path}")

    dest_dir       = ROOT / "topics" / args.topic / "pdfs"
    log_path       = (ROOT / "data" / "04_search"
                      / f"fetch_log_{date.today().isoformat()}.jsonl")
    manual_queue   = (ROOT / "data" / "04_search"
                      / f"manual_queue_{date.today().isoformat()}.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if not UNPAYWALL_EMAIL:
        print("[warn] UNPAYWALL_EMAIL not set in .env — Unpaywall source disabled.",
              file=sys.stderr)

    fetcher = OAFetcher()
    n_ok = n_skipped = 0

    with in_path.open() as fin, log_path.open("a") as flog, \
         manual_queue.open("a") as fmq:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            c = Candidate.from_dict(json.loads(line))

            if args.dry_run:
                url, used = None, None
                for src in fetcher.sources:
                    url = fetcher.resolve_url(src, c)
                    if url:
                        used = src
                        break
                result = FetchResult(
                    c, success=bool(url),
                    source=f"probe:{used or 'none'}",
                    error=None if url else "no OA URL across sources",
                )
            else:
                result = fetcher.fetch(c, dest_dir)

            flog.write(json.dumps(result.to_log_dict(), ensure_ascii=False) + "\n")
            flog.flush()
            if not result.success and result.source == "skip:not_oa":
                fmq.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
                fmq.flush()

            mark = "✓" if result.success else "✗"
            print(f"  {mark} {result.source:25s}  {c.doi[:60]}")

            if result.success:
                n_ok += 1
            else:
                n_skipped += 1
            if args.max and n_ok >= args.max:
                break

    print(f"\nDone — {n_ok} fetched, {n_skipped} skipped/failed.")
    print(f"  Log:          {log_path}")
    print(f"  Manual queue: {manual_queue}")
    print(f"  PDFs:         {dest_dir}")


if __name__ == "__main__":
    main()
