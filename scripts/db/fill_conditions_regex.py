"""
Fill missing reaction conditions (T, P, WHSV, GHSV, catalyst loading) for primary papers
by scanning enriched chunks with regex — no LLM calls needed.

Three-tier logic per evidence unit:
  1. Found in same chunk or ±N neighbours  →  fill directly (most reliable)
  2. Only one unique value in whole paper  →  fill directly (likely global condition)
  3. Multiple values found in whole paper  →  fill temperature_note with list; leave field NULL

Updates evidence_units in-place. Only touches rows where the field is currently NULL.

Usage:
  python3 scripts/db/fill_conditions_regex.py          # all primary papers
  python3 scripts/db/fill_conditions_regex.py --doi 10.1021_acs.iecr.2c03873
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

ROOT         = Path(__file__).resolve().parents[2]
DB_PATH      = ROOT / "db" / "catalysis.db"
ENRICHED_DIR = ROOT / "data" / "02_enriched"

NEIGHBOUR_WINDOW = 2   # chunks before/after to search first

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

def _temp_c(text: str) -> list[float]:
    """Extract temperature values in °C, handling all common PDF encoding artefacts.

    Variants seen in corpus:
      "450 °C"          — standard (° = U+00B0)
      "450 ◦C"          — ring-above character (U+25E6 or U+02DA), most common
      "450 ℃"           — special Celsius symbol (U+2103)
      "450 (cid:4)C"    — font mapping failure
      "4508C"           — garbled: 450 + '8' (mangled degree) + C (4-digit artefact)

    All results are sanity-clamped to 150–800 °C for MTA reactions.
    Matches directly preceded by a non-reaction step word (calcined at …,
    dried at …, NH3-TPD ramp, regeneration) are skipped — those temperatures
    must not pose as the reaction temperature.
    """
    results = []

    def _add(val, start=None):
        if start is not None and _step_before(text, start):
            return
        if 150 <= val <= 800:
            results.append(float(val))

    # Ranges "400-450 °C": emit BOTH endpoints so multi-value resolution sees
    # them — a bare upper endpoint must not pose as THE reaction temperature
    for m in re.finditer(r"\b(\d{3})\s*[-–—~]\s*(\d{3})\s*(?:[°◦∘]\s*[Cc]\b|℃)", text):
        _add(float(m.group(1)), m.start())
        _add(float(m.group(2)), m.start())

    # Standard °C (U+00B0)
    for m in re.finditer(r"\b(\d{3})\s*°\s*[Cc]\b", text):
        _add(float(m.group(1)), m.start())

    # Ring-above ◦C  (U+25E6 or U+02DA)
    for m in re.finditer(r"\b(\d{3})\s*[◦∘]\s*[Cc]\b", text):
        _add(float(m.group(1)), m.start())

    # Special Celsius symbol ℃ (U+2103)
    for m in re.finditer(r"\b(\d{3})\s*℃", text):
        _add(float(m.group(1)), m.start())

    # CID encoding: "450 (cid:N)C"
    for m in re.finditer(r"\b(\d{3})\s*\(cid:\d+\)\s*[Cc]\b", text):
        _add(float(m.group(1)), m.start())

    # Garbled degree: "4508C" → extract first 3 digits
    # Match 4-digit number where first 3 are in range and 4th is a garbled char
    for m in re.finditer(r"\b([3-7]\d{2})[0-9][Cc]\b", text):
        _add(float(m.group(1)), m.start())

    # Kelvin (explicit K, range 423–1073 K = 150–800 °C)
    for m in re.finditer(r"\b(\d{3,4})\s*K\b", text):
        k = float(m.group(1))
        if 423 <= k <= 1073 and not _step_before(text, m.start()):
            results.append(round(k - 273.15, 1))

    return results


# A non-reaction step governs a value only as a TREATMENT VERB heading the
# value's phrase ("calcined at", "reduced under", "dried overnight") — never
# as an adjective ("the as-calcined catalyst", "over the reduced catalyst").
_STEP = re.compile(
    r"\b(?:calcin\w*|dried|drying|desorption|tpd|regenerat\w*"
    r"|reduc(?:ed|tion|ing)|pretreat\w*|aged|aging|sinter\w*"
    r"|vaporiz\w*|preheat\w*)"
    r"\s+(?:(?:peak|peaks|profile|profiles|temperature|temperatures"
    r"|step|ramp)\s+)?"
    r"(?:at|to|in|under|between|for|with|of|overnight)\b", re.I)
# clause boundaries: punctuation must be followed by whitespace ("4.5 h" and
# "vol.%" are not boundaries) and "and" joining two values ("between 300 and
# 600 °C") is not a boundary either
_CLAUSE = re.compile(r"[.,;](?=\s)|\band\b(?!\s*\d|\s*$)|\bthen\b|\bbefore\b"
                     r"|\bafter\b|followed\s+by", re.I)
# a reaction verb starts the value's own governing context — the look-back
# stops there instead of at the nearest comma, so step descriptions that
# contain commas ("calcined in static air, heated to 550 °C") stay in scope
_RXVERB = re.compile(r"test|evaluat|react|perform|measur|carried\s+out", re.I)

def _step_before(text: str, start: int) -> bool:
    """Does a non-reaction step word govern the value at `start`?

    Walks clause fragments right-to-left from the value, stopping at the
    nearest reaction verb; parenthetical specs ("(40 mL min-1, 2 h)") are
    masked first so their commas cannot cut a step word out of scope."""
    window = re.sub(r"\([^)]*\)", " ", text[max(0, start - 120):start])
    scope = []
    for frag in reversed(_CLAUSE.split(window)):
        scope.append(frag)
        if _RXVERB.search(frag):
            break
    return bool(_STEP.search(" ".join(reversed(scope))))


def _pressure_mpa(text: str) -> list[float]:
    results = []
    for m in re.finditer(r"(\d+\.?\d*)\s*MPa", text, re.I):
        results.append(float(m.group(1)))
    for m in re.finditer(r"(\d+\.?\d*)\s*bar\b", text, re.I):
        results.append(round(float(m.group(1)) * 0.1, 4))
    for m in re.finditer(r"(\d+\.?\d*)\s*atm\b", text, re.I):
        results.append(round(float(m.group(1)) * 0.101325, 4))
    for m in re.finditer(r"(\d+\.?\d*)\s*kPa\b", text, re.I):
        results.append(round(float(m.group(1)) / 1000, 4))
    return results


def _whsv(text: str) -> list[float]:
    results = []
    # "WHSV of 2 h-1", "WHSV = 2 h-1", "WHSV 2 h-1" — (?:[=:]|of)? is a real
    # alternation; the old [=:of\s] was a one-CHARACTER class that could never
    # match the word "of"
    for m in re.finditer(
        r"WHSV\s*(?:[=:]|of)?\s*(\d+\.?\d*)\s*(?:h[-−]1|h\^[-−]?1|/h|·h[-−]1)",
        text, re.I
    ):
        results.append(float(m.group(1)))
    # looser (no unit anchor): require an explicit separator so a citation
    # year ("WHSV 2021") cannot match
    for m in re.finditer(r"WHSV\s*(?:[=:]|of)\s*(\d+\.?\d*)", text, re.I):
        results.append(float(m.group(1)))
    return list(dict.fromkeys(results))   # deduplicate preserving order


def _ghsv(text: str) -> list[float]:
    results = []
    # leading digit required: "GHSV," must not capture a bare comma
    for m in re.finditer(
        r"GHSV\s*(?:[=:]|of)?\s*(\d[\d,]*\.?\d*)\s*(?:mL|ml|cm3|h[-−]1|/h)",
        text, re.I
    ):
        val = float(m.group(1).replace(",", ""))
        results.append(val)
    for m in re.finditer(r"GHSV\s*(?:[=:]|of)\s*(\d[\d,]*\.?\d*)", text, re.I):
        val = float(m.group(1).replace(",", ""))
        results.append(val)
    return list(dict.fromkeys(results))


def _catalyst_loading(text: str) -> list[float]:
    results = []
    # "0.5 g catalyst", "1.2 g of NZ-60 was packed"
    for m in re.finditer(
        r"(\d+\.?\d*)\s*g\s+(?:of\s+)?(?:catalyst|zeolite|sample|ZSM|HZSM|\w+-\d+)",
        text, re.I
    ):
        val = float(m.group(1))
        if 0.01 <= val <= 20:   # sanity range in grams
            results.append(val)
    # "catalyst loading of 0.5 g"
    for m in re.finditer(r"catalyst\s+loading\s+of\s+(\d+\.?\d*)\s*g", text, re.I):
        results.append(float(m.group(1)))
    return list(dict.fromkeys(results))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_rounded(vals: list[float], decimals: int = 0) -> list[float]:
    """Round and deduplicate, e.g. [449.85, 450.0] → [450.0]."""
    rounded = [round(v, decimals) for v in vals]
    seen, out = set(), []
    for v in rounded:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _resolve(
    local_vals: list[float],
    global_vals: list[float],
    field_name: str,
    decimals: int = 0,
) -> tuple[Optional[float], Optional[str]]:
    """
    Returns (value_to_fill, note_to_fill).
    One of them is None.
    """
    # 1. Local hit
    uniq_local = _unique_rounded(local_vals, decimals)
    if len(uniq_local) == 1:
        return uniq_local[0], None

    # 2. Global single value
    uniq_global = _unique_rounded(global_vals, decimals)
    if len(uniq_global) == 1:
        return uniq_global[0], None

    # 3. Multiple → note
    if uniq_global:
        note = f"multiple {field_name}: {', '.join(str(v) for v in sorted(uniq_global))}"
        return None, note

    return None, None


# ---------------------------------------------------------------------------
# Per-paper processing
# ---------------------------------------------------------------------------

def _load_chunks(doi_slug: str) -> list[dict]:
    path = ENRICHED_DIR / f"{doi_slug}.enriched.jsonl"
    if not path.exists():
        return []
    chunks = [json.loads(line) for line in path.open(encoding="utf-8")]
    # Sort by page then chunk_index for neighbour lookup
    chunks.sort(key=lambda c: (c.get("page", 0), c.get("chunk_index", 0)))
    return chunks


def process_paper(conn: sqlite3.Connection, doi_slug: str) -> dict:
    doi = doi_slug.replace("_", "/")
    chunks = _load_chunks(doi_slug)
    if not chunks:
        return {"skipped": True, "reason": "no enriched file"}

    # Build chunk_id → index map for neighbour lookup
    id_to_idx = {c.get("chunk_id", f"chunk_{i:04d}"): i for i, c in enumerate(chunks)}

    # Collect paper-wide values (global fallback)
    full_text = " ".join(c.get("text", "") for c in chunks)
    global_T    = _temp_c(full_text)
    global_P    = _pressure_mpa(full_text)
    global_W    = _whsv(full_text)
    global_G    = _ghsv(full_text)
    global_L    = _catalyst_loading(full_text)

    # Fetch evidence units with missing conditions
    rows = conn.execute("""
        SELECT evidence_id, source_chunk_id,
               temperature_c, pressure_mpa, whsv, ghsv, catalyst_loading_g
        FROM evidence_units
        WHERE source_review_doi = ?
    """, (doi,)).fetchall()

    stats = {"updated": 0, "noted": 0, "unchanged": 0}

    for ev_id, chunk_id, cur_T, cur_P, cur_W, cur_G, cur_L in rows:
        # Build local text (chunk + neighbours)
        local_text = ""
        if chunk_id and chunk_id in id_to_idx:
            idx = id_to_idx[chunk_id]
            lo  = max(0, idx - NEIGHBOUR_WINDOW)
            hi  = min(len(chunks), idx + NEIGHBOUR_WINDOW + 1)
            local_text = " ".join(chunks[i].get("text", "") for i in range(lo, hi))

        local_T = _temp_c(local_text)
        local_P = _pressure_mpa(local_text)
        local_W = _whsv(local_text)
        local_G = _ghsv(local_text)
        local_L = _catalyst_loading(local_text)

        updates: dict[str, object] = {}
        notes: list[str] = []

        if cur_T is None:
            val, note = _resolve(local_T, global_T, "T(°C)", decimals=0)
            if val is not None:
                updates["temperature_c"] = val
            elif note:
                notes.append(note)

        if cur_P is None:
            val, note = _resolve(local_P, global_P, "P(MPa)", decimals=2)
            if val is not None:
                updates["pressure_mpa"] = val
            elif note:
                notes.append(note)

        if cur_W is None:
            val, note = _resolve(local_W, global_W, "WHSV", decimals=2)
            if val is not None:
                updates["whsv"] = val
            elif note:
                notes.append(note)

        if cur_G is None:
            val, note = _resolve(local_G, global_G, "GHSV", decimals=0)
            if val is not None:
                updates["ghsv"] = val
            elif note:
                notes.append(note)

        if cur_L is None:
            val, note = _resolve(local_L, global_L, "catalyst_loading(g)", decimals=3)
            if val is not None:
                updates["catalyst_loading_g"] = val
            elif note:
                notes.append(note)

        if notes:
            updates["temperature_note"] = "; ".join(notes)

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE evidence_units SET {set_clause} WHERE evidence_id = ?",
                list(updates.values()) + [ev_id],
            )
            if any(k != "temperature_note" for k in updates):
                stats["updated"] += 1
            else:
                stats["noted"] += 1
        else:
            stats["unchanged"] += 1

    conn.commit()
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill reaction conditions for primary papers via regex (no LLM)"
    )
    parser.add_argument("--doi", help="Single DOI slug (underscores)")
    args = parser.parse_args()

    with sqlite3.connect(DB_PATH) as conn:
        # self-migrate: the columns this script fills were added after the
        # first release; make the script runnable against an older DB
        have = {r[1] for r in conn.execute("PRAGMA table_info(evidence_units)")}
        for col, typ in (("catalyst_loading_g", "REAL"), ("temperature_note", "TEXT")):
            if col not in have:
                conn.execute(f"ALTER TABLE evidence_units ADD COLUMN {col} {typ}")
        conn.commit()

        if args.doi:
            slugs = [args.doi]
        else:
            rows = conn.execute(
                "SELECT doi FROM papers WHERE paper_type = 'primary'"
            ).fetchall()
            slugs = [r[0].replace("/", "_") for r in rows]

        total_updated = total_noted = 0
        for slug in sorted(slugs):
            result = process_paper(conn, slug)
            if result.get("skipped"):
                print(f"  [skip] {slug}: {result['reason']}")
                continue
            u, n, x = result["updated"], result["noted"], result["unchanged"]
            total_updated += u
            total_noted   += n
            flag = " ⚠ multi-T" if n > 0 else ""
            print(f"  {slug}: +{u} filled, {n} noted, {x} unchanged{flag}")

        print(f"\nDone. {total_updated} units filled with conditions, "
              f"{total_noted} units got temperature_note (needs review).")


if __name__ == "__main__":
    main()
