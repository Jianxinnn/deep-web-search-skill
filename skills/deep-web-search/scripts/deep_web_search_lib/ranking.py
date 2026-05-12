from __future__ import annotations

import textwrap
from datetime import datetime
from typing import Any

from .models import CONCEPT_PHRASES, SourceRecord, slug, stable_id


def dedupe_sources(sources: list[SourceRecord]) -> list[SourceRecord]:
    seen: set[str] = set()
    output: list[SourceRecord] = []
    for source in sources:
        key = (
            source.doi.lower()
            or source.arxiv_id.lower()
            or source.pubmed_id.lower()
            or source.semantic_scholar_id.lower()
            or source.openalex_id.lower()
            or source.url.lower()
            or slug(source.title)
        )
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(source)
    return output


def search_phrases(question: str) -> list[str]:
    text = slug(question)
    matched = [phrase for phrase in CONCEPT_PHRASES if phrase in text]
    if "allosteric" in text:
        matched.append("allostery")
    return list(dict.fromkeys(matched))


def source_matches(target_phrases: list[str], source: SourceRecord) -> list[str]:
    haystack = slug(f"{source.title} {source.abstract} {source.snippet}")
    matches = [phrase for phrase in target_phrases if phrase in haystack]
    if "domain insertion" in haystack and "domain insertion" not in matches:
        matches.append("domain insertion")
    if "alloster" in haystack and "allostery/allosteric" not in matches:
        matches.append("allostery/allosteric")
    if "switch" in haystack and "switch behavior" not in matches:
        matches.append("switch behavior")
    if "biosensor" in haystack and "biosensor" not in matches:
        matches.append("biosensor")
    if "circular" in haystack and "permut" in haystack and "circular permutation" not in matches:
        matches.append("circular permutation")
    return matches[:6]


def score_sources(question: str, sources: list[SourceRecord]) -> list[SourceRecord]:
    terms = {term for term in slug(question).split() if len(term) > 2}
    current_year = datetime.now().year
    target_phrases = search_phrases(question)
    provider_bonus_by_name = {
        "arxiv": 0.08,
        "semantic_scholar": 0.07,
        "pubmed": 0.06,
        "openalex": 0.04,
        "tavily": 0.03,
    }
    for source in sources:
        haystack = set(slug(f"{source.title} {source.abstract} {source.snippet}").split())
        overlap = len(terms & haystack) / max(len(terms), 1)
        source.matches = source_matches(target_phrases, source)
        phrase_bonus = min(0.35, 0.07 * len(source.matches))
        recency = 0.0
        if source.year:
            recency = max(0.0, min(1.0, 1.0 - ((current_year - source.year) / 15.0)))
        provider_bonus = provider_bonus_by_name.get(source.provider, 0.03)
        source.score = round(min(1.0, 0.55 * overlap + 0.24 * phrase_bonus + 0.14 * recency + provider_bonus), 3)
    return sorted(sources, key=lambda item: item.score, reverse=True)


def focus_ranked_sources(question: str, sources: list[SourceRecord], max_results: int) -> list[SourceRecord]:
    text = slug(question)
    if "allosteric" in text or "domain insertion" in text or "protein switch" in text:
        focused = [source for source in sources if len(source.matches) >= 2]
        if len(focused) >= 3:
            return focused[:max_results]
    return sources[:max_results]


def evidence_rows(sources: list[SourceRecord], max_items: int) -> list[dict[str, Any]]:
    rows = []
    for source in sources[:max_items]:
        text = source.abstract or source.snippet or source.title
        rows.append(
            {
                "evidence_id": stable_id("ev", f"{source.source_id}:{text[:120]}"),
                "source_id": source.source_id,
                "claim": f"{source.title} is relevant to the search question.",
                "evidence_text": textwrap.shorten(text, width=700, placeholder="..."),
                "confidence": source.score,
                "source_locator": source.url,
                "matches": source.matches,
            }
        )
    return rows


def source_url(source: SourceRecord) -> str:
    if source.doi:
        return f"https://doi.org/{source.doi}"
    return source.url
