"""
Add papers by DOI to Zotero (no PDF upload).
Fetches Crossref metadata, classifies with Claude Haiku, creates item in correct collection.

Usage:
  python3 scripts/zotero/add_dois_to_zotero.py 10.1021/acscatal.1c01422 10.1021/acscatal.1c05481
"""

from __future__ import annotations
import sys, json, os, re, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()

import anthropic

ZOTERO_API_KEY = os.environ["ZOTERO_API_KEY"]
ZOTERO_USER_ID = os.environ["ZOTERO_USER_ID"]
BASE  = f"https://api.zotero.org/users/{ZOTERO_USER_ID}"
Z_HDR = {"Zotero-API-Key": ZOTERO_API_KEY, "Accept": "application/json"}

TAXONOMY = {
    "002_Methanol to Aromatic": {
        "direct MTA papers":
            "Primary research papers reporting experimental MTA/MTH/MTO catalyst performance "
            "(conversion %, selectivity %, BTX yield). Catalysts are typically modified ZSM-5 "
            "(Zn, Ga, P, phosphorus) or SAPO. Methanol is the feedstock.",
        "zeolite/selectivity papers":
            "Papers studying how zeolite topology, Si/Al ratio, pore/cage size, or acid site "
            "properties affect product distribution in methanol conversion.",
        "deactivation/coke":
            "Papers focused on catalyst deactivation, coke formation, coke characterisation, "
            "or regeneration in MTH/MTO/MTA reactions.",
        "methanol-mediated CO2-to-aromatics bridge":
            "Papers about bifunctional catalysts that convert CO2 via methanol to olefins "
            "or aromatics (e.g. oxide+zeolite, ZnZrO/ZSM-5).",
        "review":
            "Review or perspective articles specifically covering methanol-to-aromatics or "
            "methanol-to-hydrocarbons catalysis.",
    },
    "003_CO2 to Aromatic": {
        "direct CO2→aromatics":
            "Papers reporting direct conversion of CO2 to aromatic products (BTX).",
        "bifunctional catalysts":
            "Design or mechanistic study of bifunctional catalysts for CO2 hydrogenation.",
        "CO2→MeOH→olefins":
            "Papers on the methanol route of CO2 hydrogenation primarily targeting light olefins.",
    },
    "004_Other": {
        "review/perspective": "Broad review or perspective not fitting MTA or CO2-to-aromatic.",
        "unrelated": "Not related to methanol conversion, CO2 hydrogenation, or zeolite catalysis.",
    },
}

CLASSIFY_SYSTEM = """\
You are a research librarian specialising in heterogeneous catalysis.
Classify the paper into exactly one top-level collection and subcollection from the taxonomy.
Return ONLY valid JSON:
{
  "top_level": "<name>",
  "subcollection": "<name>",
  "has_quantitative_data": true/false,
  "pipeline_priority": "high"/"medium"/"low",
  "reasoning": "<one sentence>"
}
"""

def crossref_metadata(doi: str) -> dict:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='/')}"
    req = urllib.request.Request(url, headers={"User-Agent": "MTA-pipeline/1.0 (y.piao@uu.nl)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())["message"]
    authors = data.get("author", [])
    year = ""
    for dp in data.get("published-print", data.get("published-online", {})).get("date-parts", [[]]):
        if dp: year = str(dp[0]); break
    abstract = re.sub(r"<[^>]+>", "", data.get("abstract", "")).strip()
    return {
        "title":       (data.get("title") or [""])[0],
        "first_author": authors[0].get("family", "?") if authors else "?",
        "all_authors": authors,
        "year":        year,
        "journal":     data.get("container-title", [""])[0],
        "abstract":    abstract,
        "doi":         doi,
    }

def classify(meta: dict) -> dict:
    taxonomy_str = json.dumps(TAXONOMY, indent=2, ensure_ascii=False)
    prompt = (
        f"Taxonomy:\n{taxonomy_str}\n\n"
        f"Paper:\nTitle: {meta['title']}\nDOI: {meta['doi']}\n"
        f"Journal: {meta['journal']}\nAbstract: {meta['abstract'][:1200] or '(not available)'}"
    )
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
        system=CLASSIFY_SYSTEM,
    )
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", msg.content[0].text.strip(), flags=re.S)
    return json.loads(text)

def z_get(path: str):
    req = urllib.request.Request(f"{BASE}/{path.lstrip('/')}", headers=Z_HDR)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read()), dict(r.headers)

def z_post(path: str, payload) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/{path.lstrip('/')}",
        data=data,
        headers={**Z_HDR, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
        return json.loads(body) if body else {}

col_cache: dict = {}

def get_or_create_col(name: str, parent_key: str | None) -> str:
    cache_key = f"{parent_key}|{name}"
    if cache_key in col_cache:
        return col_cache[cache_key]
    cols, _ = z_get("collections?limit=100")
    for c in cols:
        d = c["data"]
        if d["name"] == name and (d.get("parentCollection") or None) == parent_key:
            col_cache[cache_key] = d["key"]
            return d["key"]
    result = z_post("collections", [{"name": name, "parentCollection": parent_key or False}])
    key = result["successful"]["0"]["data"]["key"]
    print(f"  [Zotero] Created collection '{name}' → {key}")
    col_cache[cache_key] = key
    return key

def already_in_zotero(doi: str) -> bool:
    items, _ = z_get("items?limit=100&itemType=journalArticle")
    return any(i["data"].get("DOI","").strip().lower() == doi.lower() for i in items)

def create_item(meta: dict, col_key: str) -> str:
    creators = []
    for a in meta.get("all_authors", []):
        creators.append({"creatorType": "author", "lastName": a.get("family",""), "firstName": a.get("given","")})
    if not creators:
        creators = [{"creatorType": "author", "lastName": meta["first_author"], "firstName": ""}]
    result = z_post("items", [{
        "itemType":         "journalArticle",
        "title":            meta["title"],
        "creators":         creators,
        "abstractNote":     meta["abstract"],
        "publicationTitle": meta["journal"],
        "date":             meta["year"],
        "DOI":              meta["doi"],
        "collections":      [col_key],
    }])
    return result["successful"]["0"]["data"]["key"]

def main(dois: list[str]) -> None:
    for doi in dois:
        print(f"\n── {doi}")
        if already_in_zotero(doi):
            print("  ✅ already in Zotero — skip")
            continue
        meta = crossref_metadata(doi)
        print(f"  {meta['first_author']} {meta['year']} — {meta['title'][:70]}")
        cls = classify(meta)
        tl, sub = cls["top_level"], cls["subcollection"]
        print(f"  → {tl} / {sub}  [{cls['pipeline_priority']}]")
        print(f"     {cls['reasoning']}")
        tl_key  = get_or_create_col(tl, None)
        sub_key = get_or_create_col(sub, tl_key)
        key = create_item(meta, sub_key)
        print(f"  ✓ Created Zotero item → {key}")
        time.sleep(0.5)

if __name__ == "__main__":
    main(sys.argv[1:])
