# Scholar Download SOP v1

## Purpose
A practical standard operating procedure for downloading academic papers through the user's Utrecht University access workflow, with emphasis on minimizing failed detours.

This SOP was derived from actual trial-and-error during literature collection workflows.

---

# 1. Default entry point

Always start from Google Scholar institutional entry:

- `https://scholar.google.com/?inst=7240083048524121927`

Do **not** default to Scopus as the first step.
Scopus may still be useful as a fallback or metadata route, but it should not be the default first entry for paper retrieval.

---

# 2. Default search strategy

For each target paper:
1. Search by **DOI** first.
2. If DOI search is poor or ambiguous, search by **full title**.
3. Prefer the result that clearly matches title + authors + venue.

---

# 3. Link priority order

When the Scholar result page appears, use this priority order:

## Priority 1 — `[PDF]` link on the right
Examples:
- `[PDF] uu.nl`
- `[PDF] springer.com`
- repository / institutional PDF mirrors

### Why
These links often lead directly to:
- repository-hosted PDFs
- publisher PDF endpoints
- downloadable files that can be saved directly

### Preferred action
- Click `[PDF]` first.
- If it opens a direct PDF URL or repository PDF page, try direct file save/download.

## Priority 2 — `Fulltext@UBU`
Use only if no workable `[PDF]` link is available.

### Why lower priority
This path may introduce:
- WorldCat resolver detours
- DOM instability
- Google reCAPTCHA layers

## Priority 3 — other article links
Examples:
- publisher article landing page
- abstract pages
- DOI landing pages

Use only if neither `[PDF]` nor `Fulltext@UBU` works.

---

# 4. Direct PDF handling rules

## If `[PDF]` opens a direct PDF URL or repository-hosted PDF
Examples:
- Utrecht repository PDF
- Springer direct PDF

### Then:
1. Prefer direct download/save from the URL.
2. Verify the downloaded file is a **real PDF**, not HTML.
3. Check:
   - `file <path>`
   - PDF header starts with `%PDF`

## Important warning
Never assume a `.pdf` filename means a real PDF.
Always verify.

---

# 5. Publisher-specific rules

## 5.1 Repository / institutional PDF (best case)
Examples:
- `uu.nl`
- repository-hosted direct PDFs

### Action
- Directly save/download.
- Usually the cleanest route.

## 5.2 Springer direct PDF
### Action
- If Scholar `[PDF] springer.com` opens direct PDF URL, save directly.
- Verify as real PDF.

## 5.3 ResearchGate PDF link
### Action
- Treat with caution.
- A visible ResearchGate PDF link may still return `403` to direct curl/download.
- If direct save fails, do not waste too much time trying to force it.
- Consider fallback to `Fulltext@UBU` or another access route.

## 5.4 ScienceDirect / Elsevier
### Action priority
1. Reach article page or PDF viewer.
2. If direct URL save works and yields a real PDF, use it.
3. If direct save yields HTML or 403, do **not** keep retrying the bare PDF link.
4. Use PDF viewer route.

### Important
For ScienceDirect-like viewer flows:
- prefer the **PDF viewer’s own print button** first
- do **not** default to raw URL pulling
- do **not** default to system print shortcuts as first choice

## 5.5 Nature / Taylor & Francis / others
### Action
- Follow the same Scholar-first logic.
- Prefer right-side `[PDF]` if available.
- Use institution access only if direct PDF route is unavailable.

---

# 6. PDF viewer rule

If access ultimately lands in a browser PDF viewer:

## Preferred order
1. Try the viewer-native print/save route first.
2. Only if that fails, consider other fallback methods.

## Important distinction
Do not confuse:
- the viewer’s own top-right print button
- with system/browser print shortcuts

The viewer-native print button is preferred.

---

# 7. Verification checklist after every download

Every downloaded candidate file must be verified.

## Required checks
- file exists in target folder
- `file <path>` reports PDF
- file header begins with `%PDF`
- file size is plausible (not tiny HTML fallback)

## If verification fails
Mark as:
- `fake_pdf`
- `html_fallback`
- `403_blocked`
- or similar status in log

---

# 8. Logging rule

Maintain a lightweight log per project.

For each attempted paper, record:
- DOI
- title
- source path used (`[PDF]`, `Fulltext@UBU`, publisher page, etc.)
- success/failure
- blocker type
- saved file path if successful

This avoids repeating the same mistakes.

---

# 9. Current known blockers

## Blocker A — `Fulltext@UBU` may trigger WorldCat + reCAPTCHA
Observed behavior:
- Scholar search works
- `Fulltext@UBU` is present
- click may open WorldCat resolver
- resolver may trigger Google reCAPTCHA subframes

## Blocker B — Scholar DOM instability
Observed behavior:
- `Fulltext@UBU` visibly exists in snapshot
- automated click may still fail due to locator timeout

## Blocker C — direct PDF URL may return HTML fallback
Observed behavior:
- especially with ScienceDirect / protected publisher flows
- direct URL may look like PDF but save as HTML

## Blocker D — browser PDF viewer toolbar not always machine-visible
Observed behavior:
- OpenClaw snapshot may show `(no interactive elements)` on Chrome PDF viewer tabs
- therefore viewer toolbar buttons may not be directly clickable through the normal element model

---

# 10. Current working lessons

## Proven successful
- Scholar `[PDF] uu.nl` → direct save → valid PDF
- Scholar `[PDF] springer.com` → direct save → valid PDF

## Proven unreliable or conditional
- `Fulltext@UBU` path due to WorldCat/reCAPTCHA
- ResearchGate direct PDF due to possible 403
- ScienceDirect direct PDF link due to HTML fallback / 403

---

# 11. Operational rule for future work

When running downloads:

1. One paper at a time when debugging a new publisher path.
2. Use this SOP strictly.
3. Do not switch entry logic mid-run unless the current branch clearly fails.
4. Report only after a concrete result:
   - valid PDF saved
   - or clearly identified blocker

---

# 12. Recommended next upgrade

Once this SOP is stable across more publishers, upgrade it into:
- a project script
- and later possibly a reusable skill

But for now, this Markdown file is the source of truth.
