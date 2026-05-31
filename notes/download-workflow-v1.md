# Full-text download workflow v1 (validated on 2026-03-16)

## Scope
Validated using Utrecht University access chain and OpenClaw managed browser.

## Verified paper
- DOI: `10.1016/j.apcatb.2021.120073`
- Title: `Catalysts design for higher alcohols synthesis by CO2 hydrogenation: Trends and future perspectives`
- Saved file: `/Users/avalont/Projects/knowledge/Science/pdfs/10.1016_j.apcatb.2021.120073.pdf`

## Working flow
1. Open Scopus through Utrecht proxy / institutional access.
2. Search by DOI.
3. From the result page, click `UBU link`.
4. In WorldCat, click `View Full Text`.
5. In the new tab, click `View PDF`.
6. In the browser PDF viewer, use `Print` → `Save`.
7. Save to `/Users/avalont/Projects/knowledge/Science/pdfs/` using DOI-based filename.

## Important note
- Direct `Download` in the PDF viewer did **not** reliably produce a real PDF file in this environment.
- Direct command-line fetching of the visible PDF URL also failed or returned HTML instead of a true PDF.
- `Print` → `Save` produced a valid PDF and is currently the reliable v1 method.

## Filename convention
Use sanitized DOI as filename:
- `10.1016_j.apcatb.2021.120073.pdf`

## Next validation targets
- `10.1021/acscatal.0c01184`
- `10.1002/anie.201507585`
- `10.1016/j.chempr.2020.10.019`
- `10.1039/c3ee41272e`
