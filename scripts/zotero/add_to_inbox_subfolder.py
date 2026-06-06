"""
Add papers to Zotero inbox subfolder.
Usage: python3 scripts/zotero/add_to_inbox_subfolder.py
"""
import os, json, time, re, sys, urllib.request, urllib.parse
from pathlib import Path

for line in (Path(__file__).parents[2] / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

ZOTERO_API_KEY = os.environ["ZOTERO_API_KEY"]
ZOTERO_USER_ID = os.environ["ZOTERO_USER_ID"]
BASE = f"https://api.zotero.org/users/{ZOTERO_USER_ID}"
Z_HDR = {"Zotero-API-Key": ZOTERO_API_KEY, "Accept": "application/json"}

def z_get(path):
    req = urllib.request.Request(f"{BASE}/{path.lstrip('/')}", headers=Z_HDR)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def z_post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE}/{path.lstrip('/')}", data=data,
        headers={**Z_HDR, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code}: {body[:300]}")

def crossref_meta(doi):
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
        "title": (data.get("title") or [""])[0],
        "all_authors": authors,
        "year": year,
        "journal": data.get("container-title", [""])[0],
        "abstract": abstract,
        "doi": doi,
    }

INBOX_KEY = "UXFJT8G3"
SUBFOLDER_NAME = "To Download"

DOIS = [
    "10.1016/j.checat.2022.05.012",
    "10.1016/j.checat.2023.100540",
    "10.1016/s1872-2067(22)64209-8",
    "10.1021/jacs.4c12145",
    "10.1021/jacs.4c01155",
    "10.1038/s41467-024-55514-1",
    "10.1021/jacs.5c06141",
    "10.1021/acscatal.3c01491",
    "10.1021/acs.iecr.2c03873",
    "10.1016/j.jcat.2025.116147",
    "10.1021/acscatal.4c02625",
    "10.1021/acscatal.3c01332",
    "10.1016/j.jechem.2025.08.080",
    "10.1016/j.fuel.2024.131728",
    "10.1021/acscatal.2c04600",
    "10.1016/j.micromeso.2023.112589",
    "10.1016/j.ces.2023.118542",
    "10.1039/d5ta01181g",
    "10.1016/j.apcata.2024.119912",
    "10.1016/j.apcata.2024.120008",
    "10.1016/j.mcat.2024.114687",
    "10.1016/j.mtchem.2025.103202",
    "10.1016/j.fuel.2023.130704",
    "10.1016/j.apcatb.2022.122047",
    "10.1016/j.mcat.2022.112702",
    "10.1016/j.fuel.2025.135207",
    "10.1016/j.micromeso.2022.112096",
    "10.1016/j.mtsust.2023.100364",
    "10.1002/cctc.202501499",
    "10.1039/d5ta07457f",
]

def main():
    # Find or create subfolder
    cols = z_get("collections?limit=100")
    subfolder_key = None
    for c in cols:
        d = c["data"]
        if d["name"] == SUBFOLDER_NAME and d.get("parentCollection") == INBOX_KEY:
            subfolder_key = d["key"]
            break
    if not subfolder_key:
        r = z_post("collections", [{"name": SUBFOLDER_NAME, "parentCollection": INBOX_KEY}])
        subfolder_key = r["successful"]["0"]["data"]["key"]
        print(f"Created '{SUBFOLDER_NAME}' → {subfolder_key}", flush=True)
    else:
        print(f"Subfolder exists → {subfolder_key}", flush=True)

    ok, fail = 0, []
    for doi in DOIS:
        try:
            m = crossref_meta(doi)
            creators = [{"creatorType": "author",
                         "lastName": a.get("family",""), "firstName": a.get("given","")}
                        for a in m["all_authors"]] or \
                       [{"creatorType": "author", "lastName": "?", "firstName": ""}]
            r = z_post("items", [{"itemType": "journalArticle",
                "title": m["title"], "creators": creators,
                "abstractNote": m["abstract"][:2000],
                "publicationTitle": m["journal"], "date": m["year"],
                "DOI": doi, "collections": [subfolder_key]}])
            key = r["successful"]["0"]["data"]["key"]
            first = m["all_authors"][0].get("family","?") if m["all_authors"] else "?"
            print(f"  ✓ {first} {m['year']}  {m['title'][:65]}", flush=True)
            ok += 1
        except Exception as e:
            print(f"  ✗ {doi}  {e}", flush=True)
            fail.append(doi)
        time.sleep(0.7)

    print(f"\nDone: {ok} added, {len(fail)} failed", flush=True)
    if fail:
        print("Failed:", fail, flush=True)

if __name__ == "__main__":
    main()
