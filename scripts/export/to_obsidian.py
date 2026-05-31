"""
Export literature notes from DB to Obsidian-compatible markdown files.

For each paper, generates a .md file with YAML frontmatter and sections:
  - Performance Data table
  - Claims
  - Preparation Methods
  - Characterization (technique → what it showed)
  - Notes (blank)

Abstract is fetched from Crossref (cached in memory per run).

Usage:
  python3 scripts/export/to_obsidian.py              # all papers
  python3 scripts/export/to_obsidian.py --doi 10.1016/j.jcat.2018.03.032
  python3 scripts/export/to_obsidian.py --topic mta
  python3 scripts/export/to_obsidian.py --topic mta --type primary

Output: outputs/obsidian/<year> <FirstAuthor> - <Journal>.md
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Optional

ROOT    = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "db" / "catalysis.db"
OUT_DIR = ROOT / "outputs" / "obsidian"

# evidence_type values that indicate characterization (not just "experimental")
CHAR_EVIDENCE_TYPES = {"in_situ", "operando", "DFT", "isotopic", "kinetic", "in-situ"}

# claim_predicate values that suggest characterization results
CHAR_PREDICATES = {
    "characterized_by", "measured_by", "confirmed_by", "revealed_by",
    "detected_by", "observed_by", "geometry_optimization", "shows",
    "indicates", "demonstrates",
}


# ---------------------------------------------------------------------------
# Crossref abstract fetch
# ---------------------------------------------------------------------------

def _fetch_abstract(doi: str) -> str:
    """Try Crossref first, fall back to OpenAlex inverted index."""
    # 1. Crossref
    try:
        url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='/')}"
        req = urllib.request.Request(url, headers={"User-Agent": "MTA-pipeline/1.0 (y.piao@uu.nl)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            msg = json.loads(r.read())["message"]
        abstract = re.sub(r"<[^>]+>", "", msg.get("abstract", "")).strip()
        if abstract:
            return abstract
    except Exception:
        pass
    # 2. OpenAlex (abstract_inverted_index)
    try:
        url = (f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi, safe='/')}"
               f"?select=abstract_inverted_index&mailto=y.piao@uu.nl")
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        inv = data.get("abstract_inverted_index") or {}
        if inv:
            words = sorted(
                ((pos, w) for w, positions in inv.items() for pos in positions),
                key=lambda x: x[0]
            )
            return " ".join(w for _, w in words)
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Obsidian filename
# ---------------------------------------------------------------------------

def _note_filename(first_author: str, year: int, journal: str) -> str:
    """e.g. '2018 Pinilla-Herrero - J. Catal..md'"""
    # Shorten journal name
    journal_short = (journal or "")
    journal_short = re.sub(r'\bJournal of\b', 'J.', journal_short)
    journal_short = re.sub(r'\bCatalysis\b', 'Catal.', journal_short)
    journal_short = re.sub(r'\bInternational Edition\b', '', journal_short).strip()
    journal_short = re.sub(r'\s+', ' ', journal_short)
    # Strip chars not allowed in filenames
    safe = re.sub(r'[/\\:*?"<>|]', '', journal_short).strip()
    return f"{year} {first_author} - {safe}.md"


# ---------------------------------------------------------------------------
# Evidence unit queries
# ---------------------------------------------------------------------------

def _get_performance(conn: sqlite3.Connection, doi: str) -> list[dict]:
    rows = conn.execute("""
        SELECT DISTINCT catalyst_system, zeolite_type, active_metal,
               methanol_conv_pct, aromatic_sel_pct, btx_sel_pct,
               temperature_c, whsv, pressure_mpa, tos_h
        FROM evidence_units
        WHERE source_review_doi = ?
          AND (methanol_conv_pct IS NOT NULL
               OR aromatic_sel_pct IS NOT NULL
               OR btx_sel_pct IS NOT NULL)
        ORDER BY catalyst_system
    """, (doi,)).fetchall()
    cols = ["catalyst_system", "zeolite_type", "active_metal",
            "methanol_conv_pct", "aromatic_sel_pct", "btx_sel_pct",
            "temperature_c", "whsv", "pressure_mpa", "tos_h"]
    return [dict(zip(cols, r)) for r in rows]


def _get_claims(conn: sqlite3.Connection, doi: str) -> list[dict]:
    rows = conn.execute("""
        SELECT DISTINCT claim_type, claim_subject, claim_predicate, claim_object
        FROM evidence_units
        WHERE source_review_doi = ?
          AND claim_type IS NOT NULL
          AND claim_object IS NOT NULL
          AND claim_type NOT IN ('unresolved_question')
          AND (evidence_type IS NULL
               OR evidence_type NOT IN ('DFT', 'in_situ', 'operando', 'in-situ', 'isotopic', 'kinetic'))
        ORDER BY claim_type, claim_object
    """, (doi,)).fetchall()

    # Deduplicate: keep unique (type, normalised_object) pairs
    seen_objects: set[tuple] = set()
    result = []
    for ctype, subj, pred, obj in rows:
        key = (ctype, re.sub(r'\s+', ' ', obj.lower().strip())[:80])
        if key not in seen_objects:
            seen_objects.add(key)
            result.append({"type": ctype, "subject": subj, "predicate": pred, "object": obj})
    return result


def _get_preparation(conn: sqlite3.Connection, doi: str) -> list[str]:
    rows = conn.execute("""
        SELECT DISTINCT catalyst_system, preparation_method
        FROM evidence_units
        WHERE source_review_doi = ?
          AND preparation_method IS NOT NULL
          AND preparation_method != ''
        ORDER BY catalyst_system
    """, (doi,)).fetchall()

    # Normalise method strings and deduplicate per (catalyst, normalised_method)
    seen: set[tuple] = set()
    results = []
    for catalyst, method in rows:
        norm_method = re.sub(r'[-\s]+', '-', method.strip().lower())  # "ion exchange" → "ion-exchange"
        cat_key = (catalyst or "").lower().strip()
        key = (cat_key, norm_method)
        if key in seen:
            continue
        seen.add(key)
        if catalyst and catalyst.lower() not in ("unknown", ""):
            results.append(f"{catalyst}: {method}")
        else:
            results.append(method)
    return results


def _get_characterization(conn: sqlite3.Connection, doi: str) -> list[str]:
    rows = conn.execute("""
        SELECT DISTINCT evidence_type, claim_subject, claim_predicate, claim_object
        FROM evidence_units
        WHERE source_review_doi = ?
          AND evidence_type IS NOT NULL
          AND claim_object IS NOT NULL
        ORDER BY evidence_type, claim_object
    """, (doi,)).fetchall()

    results = []
    seen = set()
    for ev_type, subject, predicate, obj in rows:
        if ev_type not in CHAR_EVIDENCE_TYPES:
            continue
        if not obj or len(obj) < 5:
            continue
        # Format: "[technique] subject → object"
        if subject and len(subject) > 3:
            line = f"**{ev_type}**: {subject} → {obj}"
        else:
            line = f"**{ev_type}**: {obj}"
        if line not in seen:
            seen.add(line)
            results.append(line)
    return results


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _fmt_val(v, decimals: int = 1) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):.{decimals}f}"
    except Exception:
        return str(v)


def _render_performance_table(rows: list[dict]) -> str:
    if not rows:
        return "_No quantitative performance data extracted._\n"
    header = "| Catalyst | Zeolite | Conv% | Arom. Sel% | BTX Sel% | T (°C) | WHSV | TOS (h) |"
    sep    = "|---|---|---|---|---|---|---|---|"
    lines  = [header, sep]
    for r in rows:
        lines.append(
            f"| {r['catalyst_system'] or ''} "
            f"| {r['zeolite_type'] or ''} "
            f"| {_fmt_val(r['methanol_conv_pct'])} "
            f"| {_fmt_val(r['aromatic_sel_pct'])} "
            f"| {_fmt_val(r['btx_sel_pct'])} "
            f"| {_fmt_val(r['temperature_c'], 0)} "
            f"| {_fmt_val(r['whsv'])} "
            f"| {_fmt_val(r['tos_h'])} |"
        )
    return "\n".join(lines) + "\n"


def _render_claims(claims: list[dict]) -> str:
    if not claims:
        return "_No claims extracted._\n"
    # Group by claim_type
    groups: dict[str, list[str]] = {}
    for c in claims:
        ctype = c["type"] or "other"
        subj  = c["subject"] or ""
        pred  = c["predicate"] or ""
        obj   = c["object"] or ""
        # Build one-liner
        if subj:
            sentence = f"{subj} {pred} {obj}".strip()
        else:
            sentence = f"{pred} {obj}".strip() if pred else obj
        groups.setdefault(ctype, []).append(sentence)

    lines = []
    for ctype, sentences in sorted(groups.items()):
        lines.append(f"**{ctype}**")
        for s in sentences:
            lines.append(f"- {s}")
        lines.append("")
    return "\n".join(lines)


def render_note(
    paper: dict,
    abstract: str,
    performance: list[dict],
    claims: list[dict],
    preparation: list[str],
    characterization: list[str],
) -> str:
    doi    = paper["doi"]
    title  = paper["title"] or doi
    author = paper["first_author"] or "Unknown"
    year   = paper["year"] or ""
    journal= paper["journal"] or ""
    topic  = paper["topic"] or ""
    ptype  = paper["paper_type"] or ""

    # Build tag list
    tags = ["literature"]
    if topic:
        tags.append(topic)
    if ptype:
        tags.append(ptype)

    # YAML frontmatter
    fm_tags = ", ".join(f'"{t}"' for t in tags)
    frontmatter = f"""---
title: "{title.replace('"', "'")}"
authors: "{author} et al."
year: {year}
journal: "{journal}"
doi: "{doi}"
topic: {topic}
paper_type: {ptype}
tags: [{fm_tags}]
date_added: {date.today().isoformat()}
---"""

    # Abstract
    abstract_block = abstract if abstract else "_Abstract not available._"

    # Performance
    perf_block = _render_performance_table(performance)

    # Preparation
    if preparation:
        prep_lines = "\n".join(f"- {p}" for p in preparation)
    else:
        prep_lines = "_No preparation details extracted._"

    # Characterization
    if characterization:
        char_lines = "\n".join(f"- {c}" for c in characterization)
    else:
        char_lines = "_No characterization findings extracted._"

    # Claims (only for reviews)
    if ptype == "review" and claims:
        claims_block = "\n" + _render_claims(claims)
        claims_section = f"\n## Claims\n{claims_block}"
    else:
        claims_section = ""

    return f"""{frontmatter}

# {title}

**Authors**: {author} et al. | **Year**: {year} | **Journal**: {journal}
**DOI**: [{doi}](https://doi.org/{doi})

## Abstract

{abstract_block}

## Method

{prep_lines}

## Catalytic Results

{perf_block}
## Characterization

{char_lines}{claims_section}

## Notes

"""


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process_paper(conn: sqlite3.Connection, paper: dict, fetch_abstract: bool = True) -> Path:
    doi = paper["doi"]
    print(f"  {paper['year']} {paper['first_author']} ({doi})", end=" ... ", flush=True)

    abstract = _fetch_abstract(doi) if fetch_abstract else ""
    if fetch_abstract:
        time.sleep(0.5)  # polite Crossref

    performance     = _get_performance(conn, doi)
    claims          = _get_claims(conn, doi)
    preparation     = _get_preparation(conn, doi)
    characterization = _get_characterization(conn, doi)

    note = render_note(paper, abstract, performance, claims, preparation, characterization)

    fname = _note_filename(paper["first_author"] or "Unknown", paper["year"] or 0, paper["journal"] or "")
    out_path = OUT_DIR / fname
    out_path.write_text(note, encoding="utf-8")
    print(f"✓  ({len(performance)} perf, {len(claims)} claims, {len(characterization)} char)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export literature notes to Obsidian markdown")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--doi", help="Single DOI to export")
    grp.add_argument("--topic", choices=["mta", "co2a"], help="Filter by topic")
    parser.add_argument("--type", dest="paper_type", choices=["primary", "review"],
                        help="Filter by paper type")
    parser.add_argument("--no-abstract", action="store_true",
                        help="Skip Crossref abstract fetch")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        query = "SELECT doi, title, first_author, year, journal, topic, paper_type FROM papers WHERE 1=1"
        params = []
        if args.doi:
            query += " AND doi = ?"
            params.append(args.doi)
        if args.topic:
            query += " AND topic = ?"
            params.append(args.topic)
        if args.paper_type:
            query += " AND paper_type = ?"
            params.append(args.paper_type)
        query += " ORDER BY topic, year"

        papers = [
            dict(zip(["doi", "title", "first_author", "year", "journal", "topic", "paper_type"], row))
            for row in conn.execute(query, params).fetchall()
        ]

        print(f"Exporting {len(papers)} paper(s) to {OUT_DIR}\n")
        for paper in papers:
            process_paper(conn, paper, fetch_abstract=not args.no_abstract)

    print(f"\nDone. {len(papers)} note(s) written to {OUT_DIR}")


if __name__ == "__main__":
    with sqlite3.connect(DB_PATH) as conn:
        main()
