"""
build_catalyst_records.py — Tables → per-catalyst joined records (no LLM).

Rationale (see notes/phase0-discovery-design-v1.md and the database audit
2026-06-01): each prose evidence_unit is a sentence-level claim, so the 49
structured columns are sparse by construction (only ~1.5% of rows carry a
complete catalyst+condition+performance tuple). Catalysis tables, by contrast,
are catalyst-keyed property sheets: a paper's textural / acidity / composition /
performance tables all share the same catalyst column. Joining them *within a
paper* on the catalyst label reconstructs a dense per-catalyst record — even
when no single table contains everything.

This script:
  1. groups db.table_rows back into tables (by paper + caption);
  2. classifies each table (performance / textural / acidity / composition);
  3. finds the catalyst-identity column from the header;
  4. maps each header to a canonical attribute via
     schema/table_attribute_keywords.json (unmapped headers kept verbatim);
  5. joins all of a paper's table data on the catalyst label → one wide record
     per (paper, catalyst);
  6. reports data density and projects it to the full corpus.

No LLM calls; operates purely on the existing database. Output:
  data/05_normalized/catalyst_records_<date>.jsonl
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB   = ROOT / "db" / "catalysis.db"
KW   = ROOT / "schema" / "table_attribute_keywords.json"
OUT  = ROOT / "data" / "05_normalized"

NA_TOKENS = {"", "-", "—", "–", "n.d.", "nd", "n/a", "na", "--", "/"}

# Docling/PDF text artifacts: ligature glyphs surface as /uniFB0x or as the
# unicode ligatures themselves; fix before any matching.
_LIGATURES = {
    "/uniFB00": "ff", "/uniFB01": "fi", "/uniFB02": "fl",
    "/uniFB03": "ffi", "/uniFB04": "ffl",
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl",
    "ﬃ": "ffi", "ﬄ": "ffl",
}

_GLYPH = re.compile(r'\s*GLYPH<[^>]*>\s*')

# Subscript digits are chemistry (CO₂, H₂, C₂H₄), not footnote marks: translate
# to ASCII so "CO₂ conversion" matches the same patterns as "CO2 conversion"
# instead of degrading to "CO conversion" when subscripts are stripped.
_SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")

def fix_artifacts(s: str) -> str:
    s = (s or "").translate(_SUBSCRIPT_DIGITS)
    for bad, good in _LIGATURES.items():
        if bad in s:
            s = s.replace(bad, good)
    # Docling emits GLYPH<...> for unmapped glyphs (usually a hyphen): collapse
    # "P-ZSM GLYPH<0> 5" -> "P-ZSM-5"
    if "GLYPH<" in s:
        s = _GLYPH.sub("-", s).strip("-")
    # DOCX tables carry markdown bold and embedded newlines in headers/cells
    if "**" in s:
        s = s.replace("**", "")
    if "\n" in s or "\r" in s:
        s = s.replace("\r", " ").replace("\n", " ")
    return s

# ── keyword library ───────────────────────────────────────────────────────────

def load_kw() -> dict:
    return json.loads(KW.read_text(encoding="utf-8"))

# ── header / value cleaning ───────────────────────────────────────────────────

_FOOTNOTE = re.compile(r'\[[a-zA-Z0-9]\]')
_BRACKET  = re.compile(r'[\[\(]([^\]\)]*)[\]\)]')
# superscript footnote marks + non-digit subscripts; subscript DIGITS are
# excluded (U+2080–U+2089) — fix_artifacts already translated them to ASCII
_SUPER    = re.compile(r'[ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖ¹²³⁰-ⁿ₊-₟]+')
# trailing footnote letter: "T_a", "P b", "R^c", "Conv.a"  (a single a–f after a
# separator at the end of the header) — these are footnote refs, not the name.
_TRAIL_FN = re.compile(r'[\s_^.]+[a-f]$', re.IGNORECASE)
_UNIT_HINT = re.compile(
    r'%|°|g[⁻\-]|h[⁻\-]|mol|m²|m2|cm³|cm3|\bg\b|wt|μ|µ|nm|kj|mpa|bar|\bk\b|°c',
    re.IGNORECASE)

def clean_header(h: str) -> tuple[str, str | None]:
    """Return (clean_name, unit). 'S_BET[a] [m² g⁻¹]' -> ('S_BET', 'm² g⁻¹')."""
    h = fix_artifacts((h or "").strip())
    h = _FOOTNOTE.sub("", h)
    unit = None
    for grp in _BRACKET.findall(h):
        if _UNIT_HINT.search(grp):
            unit = grp.strip()
    name = _BRACKET.sub("", h)
    name = _SUPER.sub("", name)               # strip superscript footnote marks
    name = re.sub(r'\s+', ' ', name).strip(" :_^.")
    # slash-notation units ("temp/ K", "T / °C", "GHSV/h-1") never sit in
    # brackets, so the bracket pass above misses them; capture the tail when it
    # looks like a unit (a bare "Si/Al" or "B/L" tail does not)
    if unit is None:
        m = re.search(r'\s*/\s*([^/]+?)\s*$', name)
        if m and len(m.group(1)) <= 12 and _UNIT_HINT.search(m.group(1)):
            unit = m.group(1).strip()
            name = name[:m.start()].strip(" :_^.")
    # strip a trailing single-letter footnote ref, but never collapse the whole
    # header to empty (e.g. a genuine 1-char header stays)
    stripped = _TRAIL_FN.sub("", name).strip(" :_^.")
    if stripped:
        name = stripped
    return name, unit

def parse_value(v) -> tuple[float | None, str]:
    """Return (numeric_or_None, raw_string)."""
    if v is None:
        return None, ""
    s = fix_artifacts(str(v).strip())
    if s.lower() in NA_TOKENS:
        return None, s
    s2 = _FOOTNOTE.sub("", s).strip()
    # collapse spaces inside numbers from PDF tokenization: "6 . 1" -> "6.1",
    # "32. 8" -> "32.8" (only between digit/decimal neighbours)
    s2 = re.sub(r'(?<=[\d.])\s+(?=[\d.])', '', s2)
    m = re.match(r'^([\d.]+)\s*[–\-~to]+\s*([\d.]+)$', s2)   # range -> midpoint
    if m:
        try:
            return (float(m.group(1)) + float(m.group(2))) / 2, s
        except ValueError:
            pass
    m = re.match(r'^[~<>≈]?\s*(-?\d+\.?\d*)', s2)            # leading number
    if m:
        try:
            return float(m.group(1)), s
        except ValueError:
            pass
    return None, s

def slug(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', (s or "").lower()).strip('_') or "col"

_NUMERIC_LABEL = re.compile(r'^[\d.\s%/+-]+$')

def is_numeric_label(s: str) -> bool:
    """A catalyst label that is only digits/punctuation is a mis-detected
    catalyst column (e.g. a value column), not a catalyst name."""
    return bool(_NUMERIC_LABEL.match((s or "").strip()))

def is_headerless(headers: list[str]) -> bool:
    """Docling returns positional integer column names ('0','1',...) when it
    fails to find a header row; such tables can't be mapped to attributes."""
    clean = [str(h).strip() for h in headers]
    positional = sum(1 for h in clean
                     if h == "" or re.fullmatch(r'\d+', h) or h.lower() == "nan")
    return positional >= max(1, len(clean)) * 0.6

def norm_label(s: str) -> str:
    """Light within-paper join key: trim, drop footnotes, unify hyphens/space.
    Deliberately conservative — does NOT merge chemically distinct forms
    (H- vs NH4- vs K-), only surface variants."""
    s = fix_artifacts(str(s or ""))
    s = _FOOTNOTE.sub("", s).strip()
    s = s.replace("–", "-").replace("‐", "-").replace("−", "-")
    s = re.sub(r'\s+', ' ', s)
    return s

def clean_label(s: str) -> str:
    """Display form of a catalyst label (artifacts fixed, whitespace tidy)."""
    return re.sub(r'\s+', ' ', fix_artifacts(str(s or "")).strip())

_SEP = re.compile(r'[\s\-_/()\[\].,;:]+')

def fuzzy_key(s: str) -> str:
    """Aggressive WITHIN-PAPER join key: lowercase and drop all separators, so
    surface variants merge (Zn-C-HZSM-5 = Zn/C-HZSM-5 = ZnCHZSM5) while
    chemically distinct forms stay apart (H-ZSM-5 → hzsm5 ≠ nh4-zsm-5 → nh4zsm5,
    ZSM-5(25) → zsm525 ≠ zsm550). Safe because joins are keyed per paper."""
    s = fix_artifacts(str(s or "")).lower()
    s = _FOOTNOTE.sub("", s)
    s = _SUPER.sub("", s)
    return _SEP.sub("", s)

# ── classification / column detection ─────────────────────────────────────────

def classify_table(title: str, headers: list[str], kw: dict) -> str:
    blob = (title + " " + " ".join(headers)).lower()
    scores = {t: sum(1 for k in ks if k in blob)
              for t, ks in kw["table_type_keywords"].items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"

def find_catalyst_col(headers: list[str], rows: list[list], kw: dict) -> int | None:
    low = [h.lower() for h in headers]
    # 1. explicit catalyst-id header (but not a 'skip' header like 'entry')
    for i, h in enumerate(low):
        if any(s == h.strip() for s in kw["skip_headers"]):
            continue
        if any(k in h for k in kw["catalyst_id_headers"]):
            return i
    # 2. fallback: first column whose values are mostly non-numeric strings
    for i in range(len(headers)):
        vals = [r[i] for r in rows if i < len(r)]
        if not vals:
            continue
        nonnum = sum(1 for v in vals
                     if parse_value(v)[0] is None and str(v).strip()
                     and str(v).strip().lower() not in NA_TOKENS)
        if nonnum / len(vals) > 0.6:
            return i
    return None

def _match_patterns(low: str, kw: dict) -> str | None:
    """Longest matching pattern wins, so specific patterns beat generic
    substrings regardless of their order in the library ("space-time yield"
    beats "yield", "bas/las" beats "bas"). Ties keep first-listed order."""
    best_attr, best_len = None, 0
    for pat in kw["column_patterns"]:
        for p in pat["patterns"]:
            if len(p) > best_len and p in low:
                best_attr, best_len = pat["attr"], len(p)
    return best_attr

def map_header(clean_name: str, kw: dict, unit: str | None = None) -> tuple[str, bool]:
    """Return (canonical_attr_or_slug, was_mapped)."""
    low = clean_name.lower()
    # Docling flattens two-level headers to "group / leaf" ("product
    # distribution (%) / CH4"). The LEAF names the quantity — match it first,
    # or a long group prefix swallows every sibling column into one attribute.
    if " / " in low:
        best_attr = _match_patterns(low.rsplit(" / ", 1)[1].strip(), kw)
        if best_attr:
            return best_attr, True
    best_attr = _match_patterns(low, kw)
    if best_attr:
        return best_attr, True
    # short condition headers ("T", "Ta", "P", "Pb") carry their meaning only
    # in the unit — map via the unit when the name itself is uninformative
    if unit and len(low.strip()) <= 3:
        ul = unit.lower()
        if "°c" in ul or "℃" in ul or ul.strip() in ("c", "k"):
            return "temperature_c", True
        if any(x in ul for x in ("mpa", "bar", "atm", "kpa", "psi")):
            return "pressure", True
    return slug(clean_name), False

_ACIDITY_ATTRS = ("total_acidity", "bronsted_acidity", "lewis_acidity",
                  "weak_acidity", "strong_acidity")

def normalize_unit(attr: str, value, unit):
    """Normalise units at the source so downstream analysis is consistent.
    Returns (normalised_value, canonical_unit). Conservative: converts only
    where the unit is explicit or the value is physically unambiguous."""
    if value is None:
        return value, unit
    u = (unit or "").lower()
    if attr == "temperature_c":
        # the explicit unit is authoritative; the >500 heuristic applies only
        # when no unit was captured (a unit-less value too high to be °C here)
        if "c" in u:
            return value, "°C"
        if "k" in u or value > 500:
            return round(value - 273.15, 1), "°C"
        return value, "°C"
    if attr == "pressure":
        if "mpa" in u:  return value, "MPa"
        if "bar" in u:  return round(value / 10.0, 3), "MPa"
        if "kpa" in u:  return round(value / 1000.0, 3), "MPa"
        if "psi" in u:  return round(value / 145.04, 3), "MPa"
        if "atm" in u:  return round(value / 9.869, 3), "MPa"
        return value, unit            # unitless values are already MPa-range here
    if attr in _ACIDITY_ATTRS and "mmol" in u:
        return round(value * 1000.0, 1), "umol/g"
    return value, unit

def _attr_hit(name: str, kw: dict) -> bool:
    """Does a string denote an attribute name? Excludes composition attrs that
    commonly appear *inside* catalyst names (Si/Al15-P, 3Zn-..) and would
    otherwise fool transpose detection."""
    cname, cunit = clean_header(name)
    attr, mapped = map_header(cname, kw, cunit)
    if attr in ("si_al_ratio", "metal_loading_wt"):
        return False
    return mapped

def is_transposed(headers: list[str], rows: list[list], cat_col: int,
                  kw: dict) -> bool:
    """Detect catalyst-as-column tables (metrics down the first column).

    Normal: the non-catalyst HEADERS map to attributes.
    Transposed: the FIRST-COLUMN VALUES (row labels) map to attributes, while
    the other headers are catalyst names. Requires a clear margin so that
    catalyst codes containing attribute-like substrings don't trip it."""
    other = [h for j, h in enumerate(headers) if j != cat_col]
    header_hits = sum(1 for h in other if _attr_hit(h, kw))
    col_vals = [str(r[cat_col]) for r in rows if cat_col < len(r)]
    val_hits = sum(1 for v in col_vals if _attr_hit(v, kw))
    return val_hits >= 3 and val_hits >= header_hits + 2

# ── core ──────────────────────────────────────────────────────────────────────

def build(kw: dict) -> tuple[list[dict], dict]:
    conn = sqlite3.connect(DB)
    cur  = conn.cursor()
    cur.execute("""SELECT source_review_doi, primary_paper_doi, caption,
                          columns_json, row_json, source_page
                   FROM table_rows
                   WHERE columns_json IS NOT NULL AND row_json IS NOT NULL""")
    # group rows into tables, keyed by (paper, caption, header signature)
    tables: dict[tuple, dict] = {}
    for review_doi, primary_doi, caption, cols_j, row_j, page in cur.fetchall():
        try:
            headers = json.loads(cols_j)
            row     = json.loads(row_j)
        except (json.JSONDecodeError, TypeError):
            continue
        key = (review_doi, caption or "", tuple(headers))
        t = tables.setdefault(key, {
            "paper": review_doi, "primary": primary_doi,
            "caption": caption or "", "headers": headers, "rows": [],
        })
        t["rows"].append(row)
    conn.close()

    stats = {
        "tables": len(tables),
        "papers": len({t["paper"] for t in tables.values()}),
        "type_counts": Counter(),
        "mapped_cols": 0, "unmapped_cols": 0,
        "no_catalyst_col": 0, "transposed": 0, "unit_normalized": 0,
        "headerless_skipped": 0, "numeric_label_skipped": 0,
    }

    # per (paper, catalyst-label) accumulator
    records: dict[tuple, dict] = {}

    def get_rec(paper, primary, raw_label, ttype):
        rkey = (paper, fuzzy_key(raw_label))
        rec = records.get(rkey)
        if rec is None:
            rec = {
                "paper_doi": paper, "primary_paper_doi": primary,
                "catalyst_label": raw_label, "label_variants": {raw_label},
                "table_types": set(), "source_reference": None,
                "attributes": {},
            }
            records[rkey] = rec
        else:
            rec["label_variants"].add(raw_label)
            # keep the most informative (longest) surface form for display
            if len(raw_label) > len(rec["catalyst_label"]):
                rec["catalyst_label"] = raw_label
        rec["table_types"].add(ttype)
        return rec

    def put_attr(rec, attr, unit, val, mapped):
        num, raw = parse_value(val)
        if raw == "" or raw.lower() in NA_TOKENS:
            return
        stats["mapped_cols" if mapped else "unmapped_cols"] += 1
        if attr not in rec["attributes"]:          # first non-empty wins
            if num is not None:
                norm_val, canon_unit = normalize_unit(attr, num, unit)
                if norm_val != num:
                    stats["unit_normalized"] += 1
            else:
                norm_val, canon_unit = raw, unit
            entry = {"value": norm_val, "unit": canon_unit,
                     "numeric": num is not None}
            if num is not None and norm_val != num:
                entry["raw_value"] = num     # keep original for traceability
            rec["attributes"][attr] = entry

    for t in tables.values():
        headers = t["headers"]
        rows    = t["rows"]

        if is_headerless(headers):       # positional ('0','1',…) → can't map
            stats["headerless_skipped"] += 1
            continue

        ttype   = classify_table(t["caption"], headers, kw)
        stats["type_counts"][ttype] += 1

        cat_col = find_catalyst_col(headers, rows, kw)
        if cat_col is None:
            stats["no_catalyst_col"] += 1
            continue

        low = [h.lower().strip() for h in headers]
        ref_col = next((i for i, h in enumerate(low)
                        if h in kw["reference_headers"] or h.startswith("ref")), None)

        if is_transposed(headers, rows, cat_col, kw):
            # catalysts are the column HEADERS; each row label is an attribute
            stats["transposed"] += 1
            cat_cols = [j for j in range(len(headers))
                        if j != cat_col and j != ref_col]
            for row in rows:
                if cat_col >= len(row):
                    continue
                attr_name, unit = clean_header(str(row[cat_col]))
                attr, mapped = map_header(attr_name, kw, unit)
                for j in cat_cols:
                    if j >= len(row):
                        continue
                    label = clean_label(headers[j])
                    if not label or label.lower() in NA_TOKENS \
                       or is_numeric_label(label):
                        continue
                    rec = get_rec(t["paper"], t["primary"], label, ttype)
                    put_attr(rec, attr, unit, row[j], mapped)
            continue

        # normal orientation: one catalyst per row
        col_meta = []
        for j, h in enumerate(headers):
            name, unit = clean_header(h)
            attr, mapped = map_header(name, kw, unit)
            col_meta.append((attr, unit, mapped))

        for row in rows:
            if cat_col >= len(row):
                continue
            raw_label = clean_label(row[cat_col])
            if not raw_label or raw_label.lower() in NA_TOKENS \
               or is_numeric_label(raw_label):
                stats["numeric_label_skipped"] += 1
                continue
            rec = get_rec(t["paper"], t["primary"], raw_label, ttype)
            for j, val in enumerate(row):
                if j == cat_col or j >= len(col_meta):
                    continue
                if ref_col is not None and j == ref_col:
                    _, raw = parse_value(val)
                    if raw and raw.lower() not in NA_TOKENS:
                        rec["source_reference"] = raw
                    continue
                attr, unit, mapped = col_meta[j]
                put_attr(rec, attr, unit, val, mapped)

    out = []
    for rec in records.values():
        rec["table_types"] = sorted(rec["table_types"])
        rec["label_variants"] = sorted(rec["label_variants"])
        rec["merged_variants"] = len(rec["label_variants"])
        rec["n_attributes"] = len(rec["attributes"])
        out.append(rec)
    stats["records_with_merge"] = sum(1 for r in out if r["merged_variants"] > 1)
    return out, stats

# ── reporting ─────────────────────────────────────────────────────────────────

PERF_ATTRS = ("conversion", "selectivity", "yield", "space_time", "tof", "rate",
              # per-species product percentages (benzene_pct, ethylene_pct, …)
              "benzene", "toluene", "xylene", "aromatic", "olefin", "paraffin",
              "methane", "ethylene", "propylene", "btx", "product_fraction")
PROP_ATTRS = ("surface_area", "pore", "acid", "si_al", "loading", "crystallite")

def has_family(rec: dict, fams: tuple) -> bool:
    return any(any(f in a for f in fams) for a in rec["attributes"])

def report(records: list[dict], stats: dict) -> None:
    n = len(records)
    print("=" * 64)
    print("CATALYST RECORDS — built from tables only (no LLM)")
    print("=" * 64)
    print(f"tables parsed              : {stats['tables']}  "
          f"(from {stats['papers']} papers)")
    print(f"  table types              : "
          + ", ".join(f"{t}={c}" for t, c in stats['type_counts'].most_common()))
    print(f"  tables w/o catalyst col  : {stats['no_catalyst_col']}")
    print(f"  headerless tables skipped: {stats['headerless_skipped']}")
    print(f"  numeric-label rows skipped: {stats['numeric_label_skipped']}")
    print(f"  transposed tables fixed  : {stats['transposed']}")
    print(f"  values unit-normalized   : {stats['unit_normalized']} (K→°C, →MPa, mmol→µmol)")
    print(f"  records w/ merged labels : {stats.get('records_with_merge', 0)} "
          f"(fuzzy within-paper join)")
    print(f"  column cells mapped      : {stats['mapped_cols']} "
          f"(+ {stats['unmapped_cols']} kept verbatim)")
    print()
    print(f"per-catalyst records       : {n}")
    if not n:
        print("  (no records — check table capture)")
        return
    n_perf = sum(1 for r in records if has_family(r, PERF_ATTRS))
    n_prop = sum(1 for r in records if has_family(r, PROP_ATTRS))
    n_both = sum(1 for r in records
                 if has_family(r, PERF_ATTRS) and has_family(r, PROP_ATTRS))
    avg_attr = sum(r["n_attributes"] for r in records) / n
    print(f"  avg attributes / record  : {avg_attr:.1f}")
    print(f"  with performance         : {n_perf}  ({100*n_perf/n:.0f}%)")
    print(f"  with property            : {n_prop}  ({100*n_prop/n:.0f}%)")
    print(f"  with performance+property: {n_both}  ({100*n_both/n:.0f}%)")
    print(f"  with a citation (ref)    : {sum(1 for r in records if r['source_reference'])}")

    # attribute frequency
    freq = Counter()
    for r in records:
        freq.update(r["attributes"].keys())
    print("\ntop attributes by coverage:")
    for a, c in freq.most_common(20):
        print(f"  {100*c/n:5.0f}%  {c:4d}  {a}")

    # projection
    papers_with_tables = stats["papers"]
    if papers_with_tables:
        per_paper = n / papers_with_tables
        print(f"\nprojection (assuming full table capture):")
        print(f"  current  : {n} records from {papers_with_tables} papers "
              f"({per_paper:.1f}/paper)")
        print(f"  → 51-paper corpus  ≈ {per_paper*51:.0f} records")
        print(f"  → 200-paper corpus ≈ {per_paper*200:.0f} records")
    print("\nsample records:")
    for r in sorted(records, key=lambda x: -x["n_attributes"])[:5]:
        attrs = ", ".join(f"{k}={v['value']}" for k, v in
                          list(r["attributes"].items())[:6])
        print(f"  [{r['n_attributes']:2d} attrs | {','.join(r['table_types'])}] "
              f"{r['catalyst_label'][:30]}")
        print(f"        {attrs}")

# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    kw = load_kw()
    records, stats = build(kw)
    report(records, stats)
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / f"catalyst_records_{date.today().isoformat()}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(records)} records → {out_path}")

if __name__ == "__main__":
    main()
