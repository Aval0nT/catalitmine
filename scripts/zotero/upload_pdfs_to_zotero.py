"""
Upload local PDFs to Zotero with auto-classification.

For each PDF in topics/mta/pdfs/ not already in Zotero:
  1. Look up metadata via Crossref (title, authors, journal, year, abstract)
  2. Classify into the right collection via Claude Haiku (triage logic)
  3. Create a Zotero journalArticle item
  4. Upload the PDF as a child attachment
  5. Move the item to the correct subcollection

Usage:
  python3 scripts/zotero/upload_pdfs_to_zotero.py [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import uuid
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

import anthropic

# ── Bootstrap ────────────────────────────────────────────────────────────────

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
BASE    = f"https://api.zotero.org/users/{ZOTERO_USER_ID}"
Z_HDR   = {"Zotero-API-Key": ZOTERO_API_KEY, "Accept": "application/json"}

PDF_DIR = ROOT / "topics" / "mta" / "pdfs"

# ── Taxonomy (same as triage script) ─────────────────────────────────────────

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
    },
    "003_CO2 to Aromatic": {
        "direct CO2→aromatics":
            "Papers reporting direct conversion of CO2 to aromatic products (BTX) in a single "
            "reactor, typically via Fischer-Tropsch or oxide+zeolite bifunctional route.",
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

# ── Helpers ───────────────────────────────────────────────────────────────────

def slug_to_doi(slug: str) -> str:
    """Convert filename slug back to DOI: 10.1016_j.jcat.2007.04.006 → 10.1016/j.jcat.2007.04.006"""
    prefix, rest = slug.split("_", 1)   # split on FIRST underscore only
    return f"{prefix}/{rest}"


def crossref_metadata(doi: str) -> dict:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='/')}"
    req = urllib.request.Request(url, headers={"User-Agent": "MTA-pipeline/1.0 (y.piao@uu.nl)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())["message"]
        authors = data.get("author", [])
        first_author = authors[0].get("family", "?") if authors else "?"
        year = ""
        for dp in data.get("published-print", data.get("published-online", {})).get("date-parts", [[]]):
            if dp:
                year = str(dp[0])
                break
        abstract = re.sub(r"<[^>]+>", "", data.get("abstract", "")).strip()
        journal  = data.get("container-title", [""])[0]
        return {
            "title":        (data.get("title") or [""])[0],
            "first_author": first_author,
            "all_authors":  authors,
            "year":         year,
            "journal":      journal,
            "abstract":     abstract,
            "doi":          doi,
        }
    except Exception as e:
        return {"title": doi, "first_author": "?", "all_authors": [], "year": "",
                "journal": "", "abstract": "", "doi": doi, "_error": str(e)}


def classify(meta: dict) -> dict:
    taxonomy_str = json.dumps(TAXONOMY, indent=2, ensure_ascii=False)
    prompt = (
        f"Taxonomy:\n{taxonomy_str}\n\n"
        f"Paper:\nTitle: {meta['title']}\nDOI: {meta['doi']}\n"
        f"Journal: {meta['journal']}\n"
        f"Abstract: {meta['abstract'][:1200] or '(not available)'}"
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


# ── Zotero API ────────────────────────────────────────────────────────────────

def z_get(path: str):
    req = urllib.request.Request(f"{BASE}/{path.lstrip('/')}", headers=Z_HDR)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read()), dict(r.headers)


def z_post(path: str, payload, *, method="POST") -> dict:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{BASE}/{path.lstrip('/')}",
        data=data,
        headers={**Z_HDR, "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
        return json.loads(body) if body else {}


def get_or_create_col(name: str, parent_key: str | None, col_cache: dict) -> str:
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
    print(f"    [Zotero] Created collection '{name}' → {key}")
    col_cache[cache_key] = key
    return key


def create_item(meta: dict, col_key: str) -> tuple[str, int]:
    """Create journalArticle and return (itemKey, version)."""
    creators = []
    for a in meta.get("all_authors", []):
        creators.append({
            "creatorType": "author",
            "lastName":  a.get("family", ""),
            "firstName": a.get("given", ""),
        })
    if not creators:
        creators = [{"creatorType": "author", "lastName": meta["first_author"], "firstName": ""}]

    item_data = {
        "itemType":        "journalArticle",
        "title":           meta["title"],
        "creators":        creators,
        "abstractNote":    meta["abstract"],
        "publicationTitle": meta["journal"],
        "date":            meta["year"],
        "DOI":             meta["doi"],
        "collections":     [col_key],
    }
    result = z_post("items", [item_data])
    obj    = result["successful"]["0"]
    return obj["data"]["key"], obj["version"]


def upload_pdf(parent_key: str, pdf_path: Path) -> bool:
    """Create a child attachment item, then upload the PDF file to it."""
    filename  = pdf_path.name
    pdf_bytes = pdf_path.read_bytes()
    md5       = hashlib.md5(pdf_bytes).hexdigest()
    mtime     = int(pdf_path.stat().st_mtime * 1000)
    filesize  = len(pdf_bytes)

    # Step 1 — create child attachment item under the parent
    att_result = z_post("items", [{
        "itemType":    "attachment",
        "parentItem":  parent_key,
        "linkMode":    "imported_file",
        "title":       filename,
        "filename":    filename,
        "contentType": "application/pdf",
        "charset":     "",
        "collections": [],
    }])
    att_key = att_result["successful"]["0"]["data"]["key"]

    # Step 2 — get S3 upload authorisation from the attachment item
    auth_data = urllib.parse.urlencode({
        "md5": md5, "filename": filename,
        "filesize": filesize, "mtime": mtime,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/items/{att_key}/file?params=1",
        data=auth_data,
        headers={**Z_HDR,
                 "Content-Type": "application/x-www-form-urlencoded",
                 "If-None-Match": "*"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        auth = json.loads(r.read())

    if auth.get("exists"):
        print("    [upload] File already exists in Zotero storage.")
        return True

    # Step 3 — POST to S3 using multipart/form-data (params fields + file last)
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in auth["params"].items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: application/pdf\r\n\r\n'.encode()
    )
    parts.append(pdf_bytes)
    parts.append(f'\r\n--{boundary}--\r\n'.encode())
    body = b"".join(parts)

    s3_req = urllib.request.Request(
        auth["url"], data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(s3_req, timeout=120) as r:
        pass  # 201 Created

    # Step 4 — register the completed upload with Zotero
    reg_data = urllib.parse.urlencode({"upload": auth["uploadKey"]}).encode()
    reg_req  = urllib.request.Request(
        f"{BASE}/items/{att_key}/file",
        data=reg_data,
        headers={**Z_HDR,
                 "Content-Type": "application/x-www-form-urlencoded",
                 "If-None-Match": "*"},
        method="POST",
    )
    with urllib.request.urlopen(reg_req, timeout=30) as r:
        pass

    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def already_in_zotero(doi: str) -> bool:
    items, _ = z_get("items?limit=100&itemType=journalArticle")
    return any(i["data"].get("DOI","").strip().lower() == doi.lower() for i in items)


def main(dry_run: bool) -> None:
    print("=== Upload PDFs to Zotero ===\n")
    col_cache: dict[str, str] = {}

    pdfs = sorted(PDF_DIR.glob("10.*.pdf"))
    skipped, added = [], []

    for pdf in pdfs:
        doi = slug_to_doi(pdf.stem)
        print(f"── {pdf.name}")

        if already_in_zotero(doi):
            print(f"   ✅ already in Zotero — skip\n")
            skipped.append(doi)
            continue

        # 1. Crossref metadata
        meta = crossref_metadata(doi)
        if "_error" in meta:
            print(f"   ⚠ Crossref error: {meta['_error']}")
        print(f"   {meta['first_author']} {meta['year']} — {meta['title'][:70]}")

        # 2. Classify
        try:
            cls = classify(meta)
        except Exception as e:
            print(f"   ⚠ classify error: {e} — defaulting to 004_Other/review")
            cls = {"top_level": "004_Other", "subcollection": "review/perspective",
                   "has_quantitative_data": False, "pipeline_priority": "low",
                   "reasoning": str(e)}

        tl, sub = cls["top_level"], cls["subcollection"]
        prio    = cls["pipeline_priority"]
        print(f"   → {tl} / {sub}  [{prio}]")
        print(f"      {cls['reasoning']}")

        if dry_run:
            print("   [dry-run] skip upload\n")
            continue

        # 3. Ensure collections exist
        tl_key  = get_or_create_col(tl, None, col_cache)
        sub_key = get_or_create_col(sub, tl_key, col_cache)

        # 4. Create Zotero item
        item_key, version = create_item(meta, sub_key)
        print(f"   [Zotero] Item created → {item_key}")

        # 5. Upload PDF
        try:
            upload_pdf(item_key, pdf)
            print(f"   [Zotero] PDF uploaded ✓")
        except Exception as e:
            print(f"   ⚠ PDF upload failed: {e}")

        added.append(doi)
        print()
        time.sleep(0.5)

    print(f"\n=== Done: {len(added)} added, {len(skipped)} skipped ===")
    for d in added:
        print(f"  + {d}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    main(dry_run=args.dry_run)
