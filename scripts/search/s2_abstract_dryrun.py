"""
Semantic Scholar abstract retrieval dry run.

Tests two modes:
  1. Single fetch   — sequential, 1 req/s (baseline)
  2. Batch fetch    — POST /graph/v1/paper/batch, up to 500 DOIs per request

Collects DOIs from existing ref_resolved.json files, fetches abstracts,
and reports latency, abstract availability, and projected throughput.

Usage:
  python3 scripts/search/s2_abstract_dryrun.py
  python3 scripts/search/s2_abstract_dryrun.py --single-only
  python3 scripts/search/s2_abstract_dryrun.py --limit 50
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "data" / "03_evidence"

# ── env ───────────────────────────────────────────────────────────────────────

def _load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

S2_API_KEY = os.environ.get("S2_API_KEY", "")
HEADERS    = {"x-api-key": S2_API_KEY} if S2_API_KEY else {}
BASE       = "https://api.semanticscholar.org/graph/v1"
FIELDS     = "title,year,abstract,externalIds,isOpenAccess"

# ── helpers ───────────────────────────────────────────────────────────────────

_last: float = 0.0

def _get(url: str, params: dict | None = None) -> dict:
    global _last
    wait = 1.05 - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req  = urllib.request.Request(full, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        _last = time.time()
        return json.loads(r.read())


def _post(url: str, body: dict, params: dict | None = None) -> dict:
    global _last
    wait = 1.05 - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    full    = url + ("?" + urllib.parse.urlencode(params) if params else "")
    payload = json.dumps(body).encode()
    req     = urllib.request.Request(
        full, data=payload,
        headers={**HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        _last = time.time()
        return json.loads(r.read())


# ── collect DOIs from ref_resolved files ──────────────────────────────────────

def collect_dois(limit: int | None = None) -> list[str]:
    """Gather resolved DOIs from all ref_resolved.json files."""
    dois: list[str] = []
    seen: set[str]  = set()
    for path in sorted(EVID.glob("*.ref_resolved.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for entry in data.values():
            doi = (entry.get("doi") or "").strip()
            if doi and doi not in seen:
                seen.add(doi)
                dois.append(doi)
    if limit:
        dois = dois[:limit]
    return dois


# ── single fetch test ─────────────────────────────────────────────────────────

def test_single(dois: list[str], n: int = 5) -> None:
    print(f"\n{'─'*60}")
    print(f"[1] Single fetch test  (first {n} DOIs)")
    print(f"{'─'*60}")
    latencies = []
    for doi in dois[:n]:
        url = f"{BASE}/paper/DOI:{urllib.parse.quote(doi, safe='')}"
        t0  = time.time()
        try:
            data = _get(url, {"fields": FIELDS})
            elapsed = time.time() - t0
            latencies.append(elapsed)
            has_abs  = bool(data.get("abstract"))
            title    = (data.get("title") or "")[:60]
            print(f"  {elapsed:.2f}s  {'✓ abstract' if has_abs else '✗ no abstract':14s}  {doi[:50]}")
            print(f"         {title}")
        except Exception as e:
            print(f"  ✗ error  {doi[:50]}  →  {e}")

    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"\n  avg latency : {avg:.2f}s per request")
        print(f"  rate limit  : {'authenticated (API key)' if S2_API_KEY else 'unauthenticated'}")


# ── batch fetch test ──────────────────────────────────────────────────────────

def test_batch(dois: list[str]) -> None:
    print(f"\n{'─'*60}")
    print(f"[2] Batch fetch test  ({len(dois)} DOIs in one POST request)")
    print(f"{'─'*60}")
    print(f"  Endpoint: POST {BASE}/paper/batch")
    print(f"  Fields  : {FIELDS}\n")

    ids = [f"DOI:{doi}" for doi in dois]
    t0  = time.time()
    try:
        result = _post(
            f"{BASE}/paper/batch",
            body   = {"ids": ids},
            params = {"fields": FIELDS},
        )
        elapsed = time.time() - t0
    except Exception as e:
        print(f"  ✗ Batch request failed: {e}")
        return

    papers = result if isinstance(result, list) else []

    total       = len(papers)
    with_abs    = sum(1 for p in papers if p and p.get("abstract"))
    with_doi    = sum(1 for p in papers if p and (p.get("externalIds") or {}).get("DOI"))
    open_access = sum(1 for p in papers if p and p.get("isOpenAccess"))
    nulls       = sum(1 for p in papers if p is None)

    print(f"  Request time   : {elapsed:.2f}s  (for {len(dois)} DOIs)")
    print(f"  Papers returned: {total}")
    print(f"  With abstract  : {with_abs}/{total} ({with_abs/max(total,1)*100:.0f}%)")
    print(f"  Open access    : {open_access}/{total} ({open_access/max(total,1)*100:.0f}%)")
    print(f"  Not found (null): {nulls}")

    print(f"\n  Sample abstracts (first 3 with text):")
    shown = 0
    for p in papers:
        if not p or not p.get("abstract"):
            continue
        doi   = (p.get("externalIds") or {}).get("DOI", "?")
        title = (p.get("title") or "")[:60]
        abst  = (p.get("abstract") or "")[:120]
        print(f"    DOI  : {doi}")
        print(f"    Title: {title}")
        print(f"    Abs  : {abst}…")
        print()
        shown += 1
        if shown >= 3:
            break


# ── throughput projection ─────────────────────────────────────────────────────

def project_throughput(n_dois: int, batch_size: int = 500) -> None:
    print(f"\n{'─'*60}")
    print(f"[3] Throughput projection  ({n_dois} DOIs total)")
    print(f"{'─'*60}")
    n_batches    = -(-n_dois // batch_size)     # ceiling division
    batch_time_s = 5.0                           # conservative estimate per batch
    total_s      = n_batches * batch_time_s
    seq_time_s   = n_dois * 1.1                  # sequential: 1 req/s

    print(f"  Sequential (1 req/s)   : ~{seq_time_s/60:.0f} min  ({n_dois} requests)")
    print(f"  Batch (≤{batch_size}/req)      : ~{total_s:.0f}s / {n_batches} request(s)  ← S2 advantage")
    print(f"  Speedup                : ~{seq_time_s/max(total_s,1):.0f}×")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Semantic Scholar abstract retrieval dry run")
    ap.add_argument("--limit",       type=int, default=None,
                    help="Max DOIs to collect (default: all resolved)")
    ap.add_argument("--single-n",    type=int, default=5,
                    help="How many DOIs to test in single-fetch mode (default: 5)")
    ap.add_argument("--single-only", action="store_true",
                    help="Skip batch test")
    args = ap.parse_args()

    print("Semantic Scholar Abstract Retrieval — Dry Run")
    print(f"API key present: {'yes' if S2_API_KEY else 'NO (unauthenticated)'}\n")

    dois = collect_dois(limit=args.limit)
    print(f"Collected {len(dois)} unique resolved DOIs from ref_resolved.json files")

    if not dois:
        print("No DOIs found — run resolve_refs_openalex.py first.")
        return

    test_single(dois, n=args.single_n)

    if not args.single_only:
        test_batch(dois)

    project_throughput(len(dois))
    print(f"\n{'─'*60}")
    print("Done.")


if __name__ == "__main__":
    main()
