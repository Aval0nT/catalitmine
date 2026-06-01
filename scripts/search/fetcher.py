"""
fetcher.py — PaperFetcher abstract interface + shared dataclasses for Phase 0.

The discovery pipeline (discover.py) produces Candidate records; downstream
fetchers (fetch_oa.py, optional paper-fetcher-mcp plug-in, etc.) consume them
and deposit PDFs into topics/<topic>/pdfs/.

Design (Q4c, see notes/phase0-discovery-design-v1.md):
- OAFetcher (in fetch_oa.py) is the default open-source implementation
  (Unpaywall + OpenAlex oa_url + arXiv + ChemRxiv — never paywalled URLs).
- InstitutionalFetcher (wraps paper-fetcher-mcp for SSO access) is an optional
  plug-in; not shipped enabled by default, since OSS users do not have access.
- Custom backends can implement PaperFetcher and be plugged in later.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Protocol


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Candidate:
    """One discovered paper.

    Required: doi, title. Other fields enriched by later discovery stages.
    """
    doi: str
    title: str
    year: Optional[int] = None
    venue: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    abstract: Optional[str] = None
    citation_count: int = 0
    influential_citation_count: int = 0
    is_open_access: bool = False
    oa_url: Optional[str] = None
    # Provenance: where this candidate came from, e.g.
    #   ["openalex:search:<query_slug>",
    #    "s2:references_of:10.xxx",
    #    "s2:citations_of:10.yyy",
    #    "s2:recommendation"]
    source: list[str] = field(default_factory=list)
    # LLM-scored relevance 0.0–1.0 (None when --no-llm)
    relevance: Optional[float] = None
    # Short human-readable rationale from the LLM scorer
    relevance_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        return cls(**{k: v for k, v in d.items()
                      if k in cls.__dataclass_fields__})


@dataclass
class FetchResult:
    candidate: Candidate
    success: bool
    pdf_path: Optional[Path] = None
    # e.g. "unpaywall" / "openalex_oa_url" / "arxiv" / "chemrxiv" /
    #      "cache:already_exists" / "skip:not_oa" / "skip:no_doi"
    source: str = ""
    error: Optional[str] = None

    def to_log_dict(self) -> dict:
        return {
            "doi":       self.candidate.doi,
            "title":    (self.candidate.title or "")[:120],
            "success":   self.success,
            "pdf_path":  str(self.pdf_path) if self.pdf_path else None,
            "source":    self.source,
            "error":     self.error,
        }


# ── Backend protocol ──────────────────────────────────────────────────────────

class PaperFetcher(Protocol):
    """Pluggable PDF fetcher backend.

    Known implementations:
      - OAFetcher (fetch_oa.py): Unpaywall + OpenAlex + arXiv + ChemRxiv
      - InstitutionalFetcher (planned plug-in): wraps paper-fetcher-mcp
    """

    name: str

    def can_fetch(self, c: Candidate) -> bool: ...

    def fetch(self, c: Candidate, dest_dir: Path) -> FetchResult: ...


# ── DOI helpers ───────────────────────────────────────────────────────────────

def sanitize_doi(doi: str) -> str:
    """Normalize a DOI: lowercase, strip URL prefix and whitespace."""
    s = (doi or "").strip().lower()
    for pfx in ("https://doi.org/", "http://doi.org/",
                "https://dx.doi.org/", "http://dx.doi.org/",
                "doi:", "doi.org/"):
        if s.startswith(pfx):
            s = s[len(pfx):]
    return s


def doi_to_filename(doi: str) -> str:
    """Convert a DOI into the project standard PDF filename.

    `10.1016/j.apcatb.2021.120073` → `10.1016_j.apcatb.2021.120073.pdf`
    """
    return sanitize_doi(doi).replace("/", "_") + ".pdf"
