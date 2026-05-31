"""
Zotero Inbox Triage — Stage 0

Reads all papers from 001_Inbox, classifies each by abstract using Claude Haiku,
then moves them to the correct Zotero collection (creating it if needed).

Usage:
  python3 scripts/zotero/zotero_inbox_triage.py [--dry-run]

  --dry-run   Print decisions without actually moving anything in Zotero.

Requires:
  ZOTERO_API_KEY and ZOTERO_USER_ID in .env (or environment)
  ANTHROPIC_API_KEY in environment
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request
import urllib.error
from pathlib import Path

import anthropic

# ── Config ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]

def load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()

ZOTERO_API_KEY = os.environ["ZOTERO_API_KEY"]
ZOTERO_USER_ID = os.environ["ZOTERO_USER_ID"]
BASE = f"https://api.zotero.org/users/{ZOTERO_USER_ID}"
HEADERS = {"Zotero-API-Key": ZOTERO_API_KEY, "Accept": "application/json"}

# ── Collection taxonomy ──────────────────────────────────────────────────────
# Top-level name → {subcollection name → description for LLM}
TAXONOMY = {
    "002_Methanol to Aromatic": {
        "direct MTA papers":
            "Primary research papers reporting experimental MTA/MTH/MTO catalyst performance "
            "(conversion %, selectivity %, BTX yield). Catalysts are typically modified ZSM-5 "
            "(Zn, Ga, P, phosphorus) or SAPO. Methanol is the feedstock.",
        "zeolite/selectivity papers":
            "Papers studying how zeolite topology, Si/Al ratio, pore/cage size, or acid site "
            "properties affect product distribution in methanol conversion. May be mechanistic "
            "or experimental, but focus is structure–selectivity relationships.",
        "deactivation/coke":
            "Papers focused on catalyst deactivation, coke formation, coke characterisation, "
            "or regeneration in MTH/MTO/MTA reactions.",
        "methanol-mediated CO2-to-aromatics bridge":
            "Papers about bifunctional or tandem catalysts that convert CO2 via a methanol "
            "intermediate to olefins or aromatics (e.g. oxide+zeolite, ZnZrO/ZSM-5).",
    },
    "003_CO2 to Aromatic": {
        "direct CO2→aromatics":
            "Papers reporting direct or near-direct conversion of CO2 to aromatic products "
            "(BTX, toluene, xylene) in a single reactor, typically via Fischer-Tropsch or "
            "oxide+zeolite bifunctional route.",
        "bifunctional catalysts":
            "Design, characterisation, or mechanistic study of bifunctional catalysts "
            "(metal oxide + zeolite, core-shell, tandem bed) for CO2 hydrogenation.",
        "CO2→MeOH→olefins":
            "Papers focused on the methanol route of CO2 hydrogenation primarily targeting "
            "light olefins (C2=–C4=) rather than aromatics.",
    },
    "004_Other": {
        "review/perspective":
            "Broad review or perspective articles that cover multiple topics and do not fit "
            "neatly into the MTA or CO2-to-aromatic categories.",
        "unrelated":
            "Papers not related to methanol conversion, CO2 hydrogenation, or zeolite catalysis.",
    },
}

# ── Zotero helpers ───────────────────────────────────────────────────────────

def zotero_get(path: str) -> list | dict:
    url = f"{BASE}/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def zotero_post(path: str, payload: list | dict) -> dict:
    url = f"{BASE}/{path.lstrip('/')}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={**HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def zotero_patch(path: str, payload: dict, version: int) -> None:
    url = f"{BASE}/{path.lstrip('/')}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={**HEADERS,
                 "Content-Type": "application/json",
                 "If-Unmodified-Since-Version": str(version)},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=20):
        pass


def get_or_create_collection(name: str, parent_key: str | None) -> str:
    """Return collection key, creating it if it doesn't exist."""
    cols = zotero_get("collections?limit=100")
    for c in cols:
        d = c["data"]
        if d["name"] == name and (d.get("parentCollection") or None) == parent_key:
            return d["key"]
    # create
    result = zotero_post("collections", [{"name": name, "parentCollection": parent_key or False}])
    key = result["successful"]["0"]["data"]["key"]
    print(f"  [Zotero] Created collection '{name}' → {key}")
    return key


def move_item_to_collection(item_key: str, version: int,
                             current_collections: list[str],
                             target_collection_key: str,
                             inbox_key: str) -> None:
    """Replace inbox collection with target collection in item's collections list."""
    new_cols = [c for c in current_collections if c != inbox_key]
    if target_collection_key not in new_cols:
        new_cols.append(target_collection_key)
    zotero_patch(f"items/{item_key}", {"collections": new_cols}, version)

# ── LLM classification ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a research librarian specialising in heterogeneous catalysis.
Given the title and abstract of a journal article, classify it into exactly one
top-level collection and one subcollection from the taxonomy provided.

Also decide:
- has_quantitative_data: true if the paper likely reports numeric catalyst performance
  (conversion %, selectivity %, yield %, TOF, STY) in a table or results section.
- pipeline_priority: "high" (primary research with performance data, process now),
  "medium" (review with data tables, process later), "low" (mechanism/theory only, skip pipeline).

Return ONLY valid JSON, no explanation:
{
  "top_level": "<collection name>",
  "subcollection": "<subcollection name>",
  "has_quantitative_data": true/false,
  "pipeline_priority": "high"/"medium"/"low",
  "reasoning": "<one sentence>"
}
"""

def classify_paper(title: str, abstract: str, doi: str) -> dict:
    taxonomy_str = json.dumps(TAXONOMY, indent=2, ensure_ascii=False)
    user_msg = f"""Taxonomy:
{taxonomy_str}

Paper to classify:
Title: {title}
DOI: {doi}
Abstract: {abstract[:1200] if abstract else "(not available)"}
"""
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": user_msg}],
        system=SYSTEM_PROMPT,
    )
    text = msg.content[0].text.strip()
    # strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    return json.loads(text)

# ── Main ─────────────────────────────────────────────────────────────────────

def main(dry_run: bool) -> None:
    print("=== Zotero Inbox Triage ===\n")

    # Find 001_Inbox key
    cols = zotero_get("collections?limit=100")
    inbox_key = next(
        (c["data"]["key"] for c in cols if c["data"]["name"] == "001_Inbox"), None
    )
    if not inbox_key:
        print("ERROR: 001_Inbox not found in Zotero.")
        return
    print(f"001_Inbox key: {inbox_key}")

    # Get all items in inbox
    items = zotero_get(f"collections/{inbox_key}/items?limit=100&itemType=journalArticle")
    if not items:
        print("Inbox is empty — nothing to triage.")
        return
    print(f"Found {len(items)} item(s) in inbox.\n")

    results = []
    for item in items:
        d       = item["data"]
        version = item["version"]
        key     = d["key"]
        title   = d.get("title", "")
        doi     = d.get("DOI", "").strip()
        abstract = re.sub(r"<[^>]+>", "", d.get("abstractNote", "")).strip()
        author  = d.get("creators", [{}])[0].get("lastName", "?") if d.get("creators") else "?"
        year    = d.get("date", "")[:4]

        print(f"── {author} {year} | {title[:60]}")
        print(f"   DOI: {doi or 'N/A'}")

        if not abstract:
            print("   Abstract: not available — marking as low priority")
            classification = {
                "top_level": "004_Other",
                "subcollection": "review/perspective",
                "has_quantitative_data": False,
                "pipeline_priority": "low",
                "reasoning": "No abstract available for classification.",
            }
        else:
            try:
                classification = classify_paper(title, abstract, doi)
            except Exception as e:
                print(f"   LLM error: {e}")
                classification = {
                    "top_level": "004_Other",
                    "subcollection": "unrelated",
                    "has_quantitative_data": False,
                    "pipeline_priority": "low",
                    "reasoning": f"Classification failed: {e}",
                }

        tl  = classification["top_level"]
        sub = classification["subcollection"]
        prio = classification["pipeline_priority"]
        has_data = classification["has_quantitative_data"]
        reason = classification["reasoning"]

        print(f"   → {tl} / {sub}")
        print(f"      data={has_data}  priority={prio}")
        print(f"      {reason}")

        if not dry_run:
            # Ensure top-level and subcollection exist
            tl_key  = get_or_create_collection(tl, None)
            sub_key = get_or_create_collection(sub, tl_key)
            current_cols = d.get("collections", [])
            move_item_to_collection(key, version, current_cols, sub_key, inbox_key)
            print(f"   ✓ Moved to Zotero.")
        else:
            print(f"   [dry-run] would move to '{tl}/{sub}'")

        results.append({
            "doi": doi, "title": title, "author": author, "year": year,
            **classification,
        })
        print()
        time.sleep(0.3)  # be polite to both APIs

    # Summary
    print("=== Summary ===")
    high   = [r for r in results if r["pipeline_priority"] == "high"]
    medium = [r for r in results if r["pipeline_priority"] == "medium"]
    low    = [r for r in results if r["pipeline_priority"] == "low"]
    print(f"  High priority (run pipeline now): {len(high)}")
    for r in high:
        print(f"    - {r['author']} {r['year']}  {r['doi']}")
    print(f"  Medium priority (run later):      {len(medium)}")
    for r in medium:
        print(f"    - {r['author']} {r['year']}  {r['doi']}")
    print(f"  Low priority (skip pipeline):     {len(low)}")

    # Save report
    report_path = ROOT / "data" / "zotero_triage_log.jsonl"
    with open(report_path, "a") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nLog appended → {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Classify without moving items in Zotero")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
