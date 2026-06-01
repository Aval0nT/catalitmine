"""
discover.py — Phase 0 orchestrator: research query → ranked candidate JSONL.

Pipeline:

  Stage A (query)
      OpenAlex full-text search → top-K seed papers
      (with abstract + oa_url + citation count)

  Stage B (expand)
      For each seed, S2 fetch_references + fetch_citations
      Multi-seed S2 fetch_recommendations
      → candidate pool

  Stage C (enrich)
      Candidates lacking abstract → OpenAlex DOI lookup (best-effort)

  Stage D (rank)
      Dedupe by DOI; LLM relevance score via Claude Haiku
      (skip with --no-llm; falls back to citation×recency rank)

  Stage E (write)
      data/04_search/discover_<slug>_<date>.jsonl
      (one Candidate per line, sorted by relevance descending)

CLI:
  python3 scripts/search/discover.py \
        --query "methanol to aromatics ZSM-5 Brønsted acidity" \
        --top-k 15 --depth 1

  python3 scripts/search/discover.py \
        --seed-doi 10.1021/acscatal.5b00192 10.1016/j.apcatb.2021.120073 \
        --no-llm
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetcher import Candidate, sanitize_doi  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "04_search" / ".cache"
OUT_DIR   = ROOT / "data" / "04_search"

CACHE_TTL_S = 24 * 3600

# ── env / API keys ────────────────────────────────────────────────────────────

def _load_env() -> None:
    """Load .env. A .env value fills in any variable that is unset OR present
    but empty in the environment — `setdefault` alone would let an exported
    empty var (e.g. `ANTHROPIC_API_KEY=`) shadow a real key in .env."""
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

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
S2_API_KEY        = os.environ.get("S2_API_KEY", "").strip()
OPENALEX_EMAIL    = (os.environ.get("OPENALEX_EMAIL")
                     or os.environ.get("UNPAYWALL_EMAIL")
                     or os.environ.get("USER_EMAIL")
                     or "").strip()

USER_AGENT = "catalitmine/0.1 (https://github.com/Aval0nT/catalitmine)"
CLAUDE_MODEL = os.environ.get("CATALITMINE_LLM_MODEL", "claude-haiku-4-5")

# ── disk cache + polite GET ───────────────────────────────────────────────────

def _cache_key(label: str, payload: str) -> Path:
    h = hashlib.md5(f"{label}::{payload}".encode()).hexdigest()
    return CACHE_DIR / f"{label}_{h}.json"

def _cache_read(path: Path) -> Optional[dict | list]:
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > CACHE_TTL_S:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def _cache_write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


_last_oa = 0.0
_last_s2 = 0.0

# S2 auth state: an invalid/expired key returns 401/403. On first such failure
# we disable the key process-wide and fall back to the public pool, so a bad
# key in a user's .env degrades gracefully instead of zeroing out expansion.
_s2_key_disabled = False

def _s2_auth(which: str) -> dict:
    if which != "s2" or _s2_key_disabled or not S2_API_KEY:
        return {}
    return {"x-api-key": S2_API_KEY}

def _disable_s2_key() -> bool:
    """Disable the S2 key once and report whether a retry should happen."""
    global _s2_key_disabled
    if _s2_key_disabled:
        return False  # already disabled; don't loop
    _s2_key_disabled = True
    print("[warn] S2_API_KEY rejected (401/403) — falling back to the public "
          "pool (1 req/s). Remove or refresh S2_API_KEY in .env to silence.",
          file=sys.stderr)
    return True

def _http_get_json(url: str, *, headers: dict | None = None,
                   min_interval: float = 1.0, which: str = "oa") -> dict | list:
    global _last_oa, _last_s2
    last_ref = _last_oa if which == "oa" else _last_s2
    wait = min_interval - (time.time() - last_ref)
    if wait > 0:
        time.sleep(wait)
    hdrs = {**(headers or {}), **_s2_auth(which), "User-Agent": USER_AGENT}
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if which == "s2" and e.code in (401, 403) and _disable_s2_key():
            return _http_get_json(url, headers=headers,
                                  min_interval=min_interval, which=which)
        raise
    if which == "oa":
        _last_oa = time.time()
    else:
        _last_s2 = time.time()
    return json.loads(body)

def _http_post_json(url: str, payload: dict, *, headers: dict | None = None,
                    min_interval: float = 1.0, which: str = "s2") -> dict | list:
    global _last_oa, _last_s2
    last_ref = _last_oa if which == "oa" else _last_s2
    wait = min_interval - (time.time() - last_ref)
    if wait > 0:
        time.sleep(wait)
    hdrs = {**(headers or {}), **_s2_auth(which),
            "User-Agent": USER_AGENT, "Content-Type": "application/json"}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if which == "s2" and e.code in (401, 403) and _disable_s2_key():
            return _http_post_json(url, payload, headers=headers,
                                   min_interval=min_interval, which=which)
        raise
    if which == "oa":
        _last_oa = time.time()
    else:
        _last_s2 = time.time()
    return json.loads(body)


# ── OpenAlex helpers ──────────────────────────────────────────────────────────

OA_BASE = "https://api.openalex.org"

def _oa_work_to_candidate(w: dict, source_tag: str) -> Optional[Candidate]:
    doi = (w.get("doi") or "").replace("https://doi.org/", "")
    if not doi:
        return None
    # Reconstruct abstract from OpenAlex inverted index
    inv = w.get("abstract_inverted_index")
    abstract = None
    if inv:
        positions = []
        for word, idxs in inv.items():
            for i in idxs:
                positions.append((i, word))
        positions.sort()
        abstract = " ".join(w for _, w in positions)[:1500]
    venue = (((w.get("primary_location") or {}).get("source") or {})
             .get("display_name"))
    oa     = w.get("open_access") or {}
    return Candidate(
        doi=sanitize_doi(doi),
        title=w.get("title") or "",
        year=w.get("publication_year"),
        venue=venue,
        authors=[(a.get("author") or {}).get("display_name", "")
                 for a in (w.get("authorships") or [])[:5]],
        abstract=abstract,
        citation_count=w.get("cited_by_count") or 0,
        is_open_access=bool(oa.get("is_oa")),
        oa_url=oa.get("oa_url"),
        source=[source_tag],
    )

def openalex_search(query: str, top_k: int) -> list[Candidate]:
    cache = _cache_key("oa_search", f"{query}|{top_k}")
    cached = _cache_read(cache)
    if cached is not None:
        return [Candidate.from_dict(c) for c in cached]

    params = {
        "search":   query,
        "per-page": str(min(top_k, 50)),
        "filter":   "type:article",
        "sort":     "relevance_score:desc",
    }
    if OPENALEX_EMAIL:
        params["mailto"] = OPENALEX_EMAIL
    url  = f"{OA_BASE}/works?" + urllib.parse.urlencode(params)
    data = _http_get_json(url, which="oa", min_interval=0.2)
    works = data.get("results") or []
    cands = []
    slug  = _slug(query)
    for w in works[:top_k]:
        c = _oa_work_to_candidate(w, f"openalex:search:{slug}")
        if c:
            cands.append(c)
    _cache_write(cache, [c.to_dict() for c in cands])
    return cands


def openalex_enrich(c: Candidate) -> Candidate:
    """Best-effort: fill abstract / oa_url / venue from OpenAlex DOI lookup."""
    if c.abstract and c.oa_url and c.venue:
        return c
    cache = _cache_key("oa_doi", c.doi)
    cached = _cache_read(cache)
    if cached is not None:
        w = cached
    else:
        params = {}
        if OPENALEX_EMAIL:
            params["mailto"] = OPENALEX_EMAIL
        url = (f"{OA_BASE}/works/https://doi.org/"
               f"{urllib.parse.quote(c.doi, safe='')}")
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            w = _http_get_json(url, which="oa", min_interval=0.2)
        except Exception:
            return c
        _cache_write(cache, w)

    enriched = _oa_work_to_candidate(w, "openalex:enrich") or c
    # merge: keep existing source tags + relevance
    enriched.source = list(dict.fromkeys(c.source + enriched.source))
    enriched.relevance = c.relevance
    enriched.relevance_reason = c.relevance_reason
    enriched.influential_citation_count = c.influential_citation_count
    return enriched


# ── Semantic Scholar helpers ──────────────────────────────────────────────────

S2_BASE      = "https://api.semanticscholar.org/graph/v1"
S2_REC_URL   = "https://api.semanticscholar.org/recommendations/v1/papers"
S2_FIELDS    = "paperId,externalIds,title,abstract,year,authors,journal," \
               "citationCount,influentialCitationCount,isOpenAccess,openAccessPdf"
# Authentication is injected centrally in _s2_auth(); call sites pass which="s2".
# Use the faster interval only while the key is still trusted.
def _s2_interval() -> float:
    return 0.3 if (S2_API_KEY and not _s2_key_disabled) else 1.05

def _s2_paper_to_candidate(p: dict, source_tag: str) -> Optional[Candidate]:
    if not p:
        return None
    doi = ((p.get("externalIds") or {}).get("DOI") or "").strip()
    if not doi:
        return None
    venue = (p.get("journal") or {}).get("name") or ""
    return Candidate(
        doi=sanitize_doi(doi),
        title=p.get("title") or "",
        year=p.get("year"),
        venue=venue or None,
        authors=[a.get("name", "") for a in (p.get("authors") or [])[:5]],
        abstract=p.get("abstract"),
        citation_count=p.get("citationCount") or 0,
        influential_citation_count=p.get("influentialCitationCount") or 0,
        is_open_access=bool(p.get("isOpenAccess")),
        oa_url=(p.get("openAccessPdf") or {}).get("url"),
        source=[source_tag],
    )

def s2_references(doi: str, limit: int = 50) -> list[Candidate]:
    cache = _cache_key("s2_refs", f"{doi}|{limit}")
    cached = _cache_read(cache)
    if cached is not None:
        return [Candidate.from_dict(c) for c in cached]
    url = (f"{S2_BASE}/paper/DOI:{urllib.parse.quote(doi, safe='')}/references"
           f"?fields={S2_FIELDS}&limit={limit}")
    try:
        data = _http_get_json(url, which="s2",
                              min_interval=_s2_interval())
    except Exception:
        return []
    cands = []
    for item in (data.get("data") or []):
        c = _s2_paper_to_candidate(item.get("citedPaper") or {},
                                    f"s2:references_of:{doi}")
        if c:
            cands.append(c)
    _cache_write(cache, [c.to_dict() for c in cands])
    return cands

def s2_citations(doi: str, limit: int = 50) -> list[Candidate]:
    cache = _cache_key("s2_cites", f"{doi}|{limit}")
    cached = _cache_read(cache)
    if cached is not None:
        return [Candidate.from_dict(c) for c in cached]
    url = (f"{S2_BASE}/paper/DOI:{urllib.parse.quote(doi, safe='')}/citations"
           f"?fields={S2_FIELDS}&limit={limit}")
    try:
        data = _http_get_json(url, which="s2",
                              min_interval=_s2_interval())
    except Exception:
        return []
    cands = []
    for item in (data.get("data") or []):
        c = _s2_paper_to_candidate(item.get("citingPaper") or {},
                                    f"s2:citations_of:{doi}")
        if c:
            cands.append(c)
    _cache_write(cache, [c.to_dict() for c in cands])
    return cands

def s2_recommendations(seed_dois: list[str], limit: int = 50) -> list[Candidate]:
    """`more like these` from a set of seed DOIs. Requires resolving DOI → paperId."""
    # Resolve each seed DOI to a S2 paperId via /paper/DOI:<doi>
    paper_ids: list[str] = []
    for doi in seed_dois:
        cache = _cache_key("s2_id", doi)
        cached = _cache_read(cache)
        if cached is not None:
            pid = cached.get("paperId")
        else:
            url = (f"{S2_BASE}/paper/DOI:{urllib.parse.quote(doi, safe='')}"
                   "?fields=paperId")
            try:
                data = _http_get_json(url, which="s2",
                                      min_interval=_s2_interval())
            except Exception:
                continue
            _cache_write(cache, data)
            pid = (data or {}).get("paperId")
        if pid:
            paper_ids.append(pid)
    if not paper_ids:
        return []
    cache = _cache_key("s2_recs", f"{','.join(sorted(paper_ids))}|{limit}")
    cached = _cache_read(cache)
    if cached is not None:
        return [Candidate.from_dict(c) for c in cached]
    url  = f"{S2_REC_URL}?fields={S2_FIELDS}&limit={limit}"
    body = {"positivePaperIds": paper_ids}
    try:
        data = _http_post_json(url, body, which="s2",
                                min_interval=_s2_interval())
    except Exception:
        return []
    cands = []
    for p in (data.get("recommendedPapers") or []):
        c = _s2_paper_to_candidate(p, "s2:recommendation")
        if c:
            cands.append(c)
    _cache_write(cache, [c.to_dict() for c in cands])
    return cands


# ── LLM relevance scoring ─────────────────────────────────────────────────────

_LLM_PROMPT = """You screen catalysis papers for a literature-mining project.

Research focus:
{query}

Score how relevant the following paper is to the focus on a 0.0–1.0 scale:

- 0.0   completely unrelated (e.g. wrong reaction, wrong material class)
- 0.3   tangentially related (mentions one keyword but topic is elsewhere)
- 0.6   on-topic but not central (related catalyst family or related reaction)
- 0.9   directly on topic (same reaction, comparable catalyst class)
- 1.0   foundational paper for the focus

Title: {title}
Venue: {venue}
Year:  {year}
Abstract: {abstract}

Respond with a JSON object only, no prose:
{{"relevance": 0.X, "reason": "<short, ≤25 words>"}}
"""

def _score_with_claude(query: str, cands: list[Candidate], verbose: bool) -> None:
    """Mutates cands in place, setting .relevance and .relevance_reason."""
    if not ANTHROPIC_API_KEY:
        print("[warn] ANTHROPIC_API_KEY not set — skipping LLM scoring.",
              file=sys.stderr)
        return
    try:
        from anthropic import Anthropic
    except ImportError:
        print("[warn] anthropic SDK not installed — skipping LLM scoring.",
              file=sys.stderr)
        return
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    qhash = hashlib.md5(query.encode()).hexdigest()[:8]
    for i, c in enumerate(cands, 1):
        cache = _cache_key("llm_score", f"{qhash}|{c.doi}")
        cached = _cache_read(cache)
        if cached is not None:
            c.relevance = cached.get("relevance")
            c.relevance_reason = cached.get("reason")
            continue
        prompt = _LLM_PROMPT.format(
            query=query,
            title=(c.title or "")[:300],
            venue=c.venue or "",
            year=c.year or "",
            abstract=(c.abstract or "")[:1200] or "(not available)",
        )
        try:
            resp = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=120,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
            obj  = _extract_json(text) or {}
            c.relevance = float(obj.get("relevance", 0.0))
            c.relevance_reason = (obj.get("reason") or "")[:200]
            _cache_write(cache, {"relevance":     c.relevance,
                                 "reason":         c.relevance_reason})
        except Exception as e:
            if verbose:
                print(f"  [llm error] {c.doi}: {e}", file=sys.stderr)
            c.relevance = None
        if verbose and i % 10 == 0:
            print(f"  …scored {i}/{len(cands)}", file=sys.stderr)


_JSON_RE = re.compile(r'\{.*\}', re.DOTALL)

def _extract_json(text: str) -> Optional[dict]:
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ── orchestration ─────────────────────────────────────────────────────────────

def _slug(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:60]


_TAG_RE = re.compile(r'<[^>]+>')

def _clean(s: str) -> str:
    """Strip inline HTML tags (OpenAlex titles carry <sub>, <i>, etc.)."""
    return _TAG_RE.sub('', s or '').strip()


def write_shortlist(cands: list[Candidate], path: Path, query: str | None,
                    min_relevance: float = 0.0) -> int:
    """Write a human-readable markdown shortlist for manual screening.

    One block per paper, sorted as given (relevance-descending). OA papers
    are flagged so the reader can prioritize what to download by hand.
    Returns the number of papers written.
    """
    lines: list[str] = []
    lines.append(f"# Discovery shortlist — {query or 'seed expansion'}")
    lines.append("")
    lines.append(f"*{len([c for c in cands if (c.relevance or 0) >= min_relevance])} "
                 f"papers (relevance ≥ {min_relevance:.2f}), sorted by relevance.*")
    lines.append("*🔓 = open access (try direct download); others need manual / "
                 "institutional access.*")
    lines.append("")
    n = 0
    for c in cands:
        if c.relevance is not None and c.relevance < min_relevance:
            continue
        n += 1
        rel  = f"{c.relevance:.2f}" if c.relevance is not None else "—"
        oa   = " 🔓" if (c.is_open_access or c.oa_url) else ""
        meta = " · ".join(x for x in [
            c.venue or None,
            str(c.year) if c.year else None,
            f"{c.citation_count} cit" if c.citation_count else None,
        ] if x)
        lines.append(f"## [{rel}] {_clean(c.title) or '(untitled)'}{oa}")
        lines.append(f"`{c.doi}` · https://doi.org/{c.doi}"
                     + (f"  ·  {meta}" if meta else ""))
        if c.relevance_reason:
            lines.append(f"> {c.relevance_reason}")
        if c.abstract:
            lines.append("")
            lines.append(_clean(c.abstract)[:400]
                         + ("…" if len(c.abstract) > 400 else ""))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return n


def discover(query: str | None,
             seed_dois: list[str],
             *,
             top_k: int,
             depth: int,
             max_candidates: int,
             use_citations: bool,
             use_recommendations: bool,
             use_llm: bool,
             verbose: bool) -> list[Candidate]:
    # Stage A: seeds via query
    seeds: list[Candidate] = []
    if query:
        if verbose:
            print(f"[A] OpenAlex search: '{query}' (top-{top_k})")
        seeds = openalex_search(query, top_k)
        if verbose:
            print(f"    got {len(seeds)} seeds")

    for d in seed_dois:
        d = sanitize_doi(d)
        if d and d not in {s.doi for s in seeds}:
            # placeholder; will enrich later
            seeds.append(Candidate(doi=d, title="", source=["cli:seed"]))

    if not seeds:
        raise SystemExit("No seeds — supply --query and/or --seed-doi")

    # Stage B: expansion
    pool: dict[str, Candidate] = {s.doi: s for s in seeds}
    if verbose:
        print(f"[B] expanding from {len(seeds)} seeds (depth={depth})")

    for s in seeds:
        if not s.doi:
            continue
        refs  = s2_references(s.doi, limit=30) if depth >= 1 else []
        cites = s2_citations (s.doi, limit=30) if (depth >= 1 and use_citations) else []
        for c in refs + cites:
            _merge(pool, c)
        if verbose:
            print(f"    {s.doi[:40]:40s}  refs={len(refs):2d}  cites={len(cites):2d}")

    if use_recommendations and len(seeds) >= 1:
        seed_dois_for_rec = [s.doi for s in seeds if s.doi][:5]
        recs = s2_recommendations(seed_dois_for_rec, limit=50)
        if verbose:
            print(f"    s2 recommendations from {len(seed_dois_for_rec)} seeds: "
                  f"{len(recs)}")
        for c in recs:
            _merge(pool, c)

    cands = list(pool.values())
    if max_candidates and len(cands) > max_candidates:
        # Drop the lowest-citation tail first
        cands.sort(key=lambda c: c.citation_count, reverse=True)
        cands = cands[:max_candidates]

    # Stage C: enrich (abstract / oa_url backfill)
    if verbose:
        print(f"[C] enriching {len(cands)} candidates via OpenAlex …")
    for i, c in enumerate(cands):
        if not c.abstract or not c.oa_url:
            cands[i] = openalex_enrich(c)
        if verbose and (i + 1) % 25 == 0:
            print(f"    …enriched {i+1}/{len(cands)}", file=sys.stderr)

    # Stage D: LLM scoring (or fallback)
    if use_llm and query:
        if verbose:
            print(f"[D] LLM relevance scoring ({len(cands)} candidates)")
        _score_with_claude(query, cands, verbose=verbose)
        cands.sort(key=lambda c: (c.relevance is None, -(c.relevance or 0.0)))
    else:
        if verbose:
            print(f"[D] fallback ranking: citations × recency")
        cur_year = date.today().year
        def _fb_score(c: Candidate) -> float:
            rec = 1.0 / max(1, cur_year - (c.year or cur_year - 30) + 1)
            return (c.influential_citation_count or 0) * 2 \
                 + (c.citation_count or 0) * 0.1 \
                 + rec * 100
        cands.sort(key=_fb_score, reverse=True)

    return cands


def _merge(pool: dict[str, Candidate], new: Candidate) -> None:
    if not new.doi:
        return
    if new.doi not in pool:
        pool[new.doi] = new
        return
    # merge source tags; prefer richer metadata
    cur = pool[new.doi]
    cur.source = list(dict.fromkeys(cur.source + new.source))
    if not cur.abstract and new.abstract:
        cur.abstract = new.abstract
    if not cur.oa_url and new.oa_url:
        cur.oa_url = new.oa_url
        cur.is_open_access = cur.is_open_access or new.is_open_access
    if not cur.title and new.title:
        cur.title = new.title
    if not cur.venue and new.venue:
        cur.venue = new.venue
    if not cur.year and new.year:
        cur.year = new.year
    if new.citation_count > cur.citation_count:
        cur.citation_count = new.citation_count
    if new.influential_citation_count > cur.influential_citation_count:
        cur.influential_citation_count = new.influential_citation_count


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Phase 0 orchestrator: query → ranked candidate JSONL")
    ap.add_argument("--query", help="Research query for OpenAlex search")
    ap.add_argument("--seed-doi", nargs="*", default=[],
                    help="Optional seed DOIs (skip / augment OpenAlex search)")
    ap.add_argument("--top-k", type=int, default=10,
                    help="Number of OpenAlex seeds to take from search (default 10)")
    ap.add_argument("--depth", type=int, default=1,
                    help="Citation-network expansion depth (default 1)")
    ap.add_argument("--max-candidates", type=int, default=200,
                    help="Cap candidate pool size after expansion (default 200)")
    ap.add_argument("--no-citations", action="store_true",
                    help="Skip S2 citations expansion (use references only)")
    ap.add_argument("--no-recommendations", action="store_true",
                    help="Skip S2 recommendations call")
    ap.add_argument("--no-llm", action="store_true",
                    help="Skip Claude relevance scoring (rank by citations × recency)")
    ap.add_argument("--topic", default=None,
                    help="Topic tag for filename (default: derived from query)")
    ap.add_argument("--min-relevance", type=float, default=0.0,
                    help="Only list papers scoring ≥ this in the markdown shortlist "
                         "(default 0.0 = all)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not args.query and not args.seed_doi:
        ap.error("Must supply --query and/or --seed-doi")

    cands = discover(
        query=args.query,
        seed_dois=args.seed_doi,
        top_k=args.top_k,
        depth=args.depth,
        max_candidates=args.max_candidates,
        use_citations=not args.no_citations,
        use_recommendations=not args.no_recommendations,
        use_llm=not args.no_llm,
        verbose=not args.quiet,
    )

    slug = _slug(args.query or "_".join(args.seed_doi)[:60] or "seeds")
    stamp = date.today().isoformat()
    out  = OUT_DIR / f"discover_{slug}_{stamp}.jsonl"
    md   = OUT_DIR / f"shortlist_{slug}_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for c in cands:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    n_listed = write_shortlist(cands, md, args.query, args.min_relevance)

    n_oa     = sum(1 for c in cands if c.is_open_access or c.oa_url)
    n_scored = sum(1 for c in cands if c.relevance is not None)
    print(f"\n[E] wrote {len(cands)} candidates → {out}")
    print(f"    shortlist ({n_listed} papers) → {md}")
    print(f"    {n_oa} flagged OA · {n_scored} LLM-scored")
    if cands:
        print("\nTop 10:")
        for c in cands[:10]:
            rel = f"{c.relevance:.2f}" if c.relevance is not None else "  - "
            print(f"  [rel {rel} | {c.citation_count:4d} cit | {c.year or '----'}]  "
                  f"{c.doi}")
            print(f"     {(c.title or '')[:90]}")


if __name__ == "__main__":
    main()
