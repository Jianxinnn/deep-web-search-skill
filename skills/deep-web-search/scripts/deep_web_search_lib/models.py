from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROVIDERS = ["tavily", "semantic_scholar", "pubmed", "openalex", "arxiv"]
DEFAULT_WORKERS = 5
BUNDLE_FORMAT_VERSION = "deep-web-search-1.0"
BUNDLE_FILES = {
    "request": "request.json",
    "queries": "queries.jsonl",
    "sources": "sources.jsonl",
    "evidence": "evidence.jsonl",
    "brief": "brief.md",
    "provenance": "provenance.jsonl",
}
REQUIRED_BUNDLE_FILES = ["manifest.json", *BUNDLE_FILES.values()]
PROFILE_EXPANSIONS = {
    "general": ["review", "survey", "recent advances"],
    "biomol": [
        "protein design",
        "binder design",
        "diffusion models",
        "structure prediction",
        "wet lab validation",
        "benchmark",
    ],
    "agent_skills": [
        "LLM agent skill library",
        "self-improving agents",
        "tool use",
        "skill acquisition",
        "memory reflection",
        "Model Context Protocol",
    ],
}
CONCEPT_PHRASES = [
    "domain insertion",
    "insertion site",
    "allosteric protein switch",
    "allosteric switch",
    "protein switch",
    "synthetic allostery",
    "domain recombination",
    "circular permutation",
    "circularly permuted",
    "biosensor",
    "in silico",
    "computational prediction",
    "site prediction",
    "protein engineering",
    "binding affinity",
    "protein binder",
    "diffusion model",
]


@dataclass
class QueryRecord:
    query: str
    intent: str
    provider_targets: list[str]
    rationale: str = ""


@dataclass
class SourceRecord:
    source_id: str
    title: str
    provider: str
    source_type: str = "paper"
    url: str = ""
    abstract: str = ""
    snippet: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""
    pubmed_id: str = ""
    semantic_scholar_id: str = ""
    openalex_id: str = ""
    pdf_url: str = ""
    citation_count: int | None = None
    fields: list[str] = field(default_factory=list)
    score: float = 0.0
    matches: list[str] = field(default_factory=list)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def parse_year(value: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", value or "")
    return int(match.group(0)) if match else None


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
