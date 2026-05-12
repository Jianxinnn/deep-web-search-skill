#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROVIDERS = ["arxiv", "openalex"]
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
    url: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""
    pdf_url: str = ""
    score: float = 0.0
    matches: list[str] = field(default_factory=list)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "deep-web-search-skill/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def unique_query_records(records: list[QueryRecord], limit: int) -> list[QueryRecord]:
    seen: set[str] = set()
    output: list[QueryRecord] = []
    for record in records:
        key = slug(record.query)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(record)
        if len(output) >= limit:
            break
    return output


def allosteric_switch_queries(question: str, providers: list[str]) -> list[QueryRecord]:
    text = slug(question)
    if "allosteric" not in text and "domain insertion" not in text and "protein switch" not in text:
        return []
    records = [
        QueryRecord(question, "anchor", providers, "Keep the user-provided title or topic as an anchor search."),
        QueryRecord(
            "domain insertion allosteric protein switches biosensors",
            "mechanism:domain_insertion_switches",
            providers,
            "Refine long titles into the core mechanism: domain insertion plus switch output.",
        ),
        QueryRecord(
            "computational prediction domain insertion sites protein engineering",
            "mechanism:site_prediction",
            providers,
            "Find work on predicting insertion-compatible positions.",
        ),
        QueryRecord(
            "synthetic allostery domain insertion protein biosensors",
            "mechanism:synthetic_allostery",
            providers,
            "Find engineered synthetic allostery and biosensor design examples.",
        ),
        QueryRecord(
            "circular permutation biosensors protein switches",
            "mechanism:circular_permutation",
            providers,
            "Capture the circular-permutation route used by many switchable biosensors.",
        ),
    ]
    return records


def biomol_expansions_for(question: str) -> list[str]:
    text = slug(question)
    if "binder" in text or "binding" in text:
        return ["protein binder design", "binding affinity prediction", "wet lab validation", "benchmark"]
    if "diffusion" in text:
        return ["protein diffusion model", "generative protein design", "structure prediction", "benchmark"]
    if "allosteric" in text or "biosensor" in text or "domain insertion" in text:
        return ["protein switch", "synthetic allostery", "domain recombination", "biosensor design"]
    return PROFILE_EXPANSIONS["biomol"]


def make_queries(question: str, profile: str, providers: list[str], limit: int = 5) -> list[QueryRecord]:
    refined = allosteric_switch_queries(question, providers)
    if refined:
        return unique_query_records(refined, limit)

    expansions = biomol_expansions_for(question) if profile == "biomol" else PROFILE_EXPANSIONS.get(profile, PROFILE_EXPANSIONS["general"])
    queries = [QueryRecord(question, "primary", providers, "User-provided search question.")]
    for term in expansions:
        if len(queries) >= limit:
            break
        candidate = f"{question} {term}"
        if slug(candidate) != slug(question):
            queries.append(QueryRecord(candidate, f"profile:{profile}", providers, f"Profile expansion: {term}."))
    return unique_query_records(queries, limit)


def parse_year(value: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", value or "")
    return int(match.group(0)) if match else None


def search_arxiv(query: str, limit: int) -> list[SourceRecord]:
    params = urllib.parse.urlencode(
        {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    text = fetch_text(f"https://export.arxiv.org/api/query?{params}")
    root = ET.fromstring(text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    rows: list[SourceRecord] = []
    for entry in root.findall("atom:entry", ns):
        url = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        abstract = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
        authors = [
            " ".join((author.findtext("atom:name", default="", namespaces=ns) or "").split())
            for author in entry.findall("atom:author", ns)
        ]
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href", "")
        arxiv_id = url.rsplit("/", 1)[-1] if url else ""
        rows.append(
            SourceRecord(
                source_id=stable_id("src", url or title),
                title=title,
                provider="arxiv",
                url=url,
                abstract=abstract,
                authors=[name for name in authors if name],
                year=parse_year(entry.findtext("atom:published", default="", namespaces=ns) or ""),
                venue="arXiv",
                arxiv_id=arxiv_id,
                pdf_url=pdf_url,
            )
        )
    return rows


def uninvert_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            words.append((int(pos), word))
    return " ".join(word for _, word in sorted(words))


def search_openalex(query: str, limit: int) -> list[SourceRecord]:
    params = urllib.parse.urlencode({"search": query, "per-page": limit, "sort": "relevance_score:desc"})
    payload = json.loads(fetch_text(f"https://api.openalex.org/works?{params}"))
    rows: list[SourceRecord] = []
    for item in payload.get("results", []):
        title = item.get("display_name") or ""
        url = item.get("doi") or item.get("id") or ""
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        authors = [
            (((authorship.get("author") or {}).get("display_name")) or "")
            for authorship in item.get("authorships", [])
        ]
        rows.append(
            SourceRecord(
                source_id=stable_id("src", url or title),
                title=title,
                provider="openalex",
                url=url,
                abstract=uninvert_abstract(item.get("abstract_inverted_index")),
                authors=[name for name in authors if name],
                year=item.get("publication_year"),
                venue=source.get("display_name") or "",
                doi=(item.get("doi") or "").replace("https://doi.org/", ""),
                pdf_url=((location.get("pdf_url") or "") if isinstance(location, dict) else ""),
            )
        )
    return rows


SEARCHERS = {
    "arxiv": search_arxiv,
    "openalex": search_openalex,
}


def dedupe_sources(sources: list[SourceRecord]) -> list[SourceRecord]:
    seen: set[str] = set()
    output: list[SourceRecord] = []
    for source in sources:
        key = source.doi.lower() or source.arxiv_id.lower() or slug(source.title)
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
    haystack = slug(f"{source.title} {source.abstract}")
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
    for source in sources:
        haystack = set(slug(f"{source.title} {source.abstract}").split())
        overlap = len(terms & haystack) / max(len(terms), 1)
        source.matches = source_matches(target_phrases, source)
        phrase_bonus = min(0.35, 0.07 * len(source.matches))
        recency = 0.0
        if source.year:
            recency = max(0.0, min(1.0, 1.0 - ((current_year - source.year) / 15.0)))
        provider_bonus = 0.08 if source.provider == "arxiv" else 0.04
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
        text = source.abstract or source.title
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


def md_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def render_brief(
    question: str,
    profile: str,
    providers: list[str],
    queries: list[QueryRecord],
    sources: list[SourceRecord],
    evidence: list[dict[str, Any]],
) -> str:
    lines = [
        "# Deep Web Search Brief",
        "",
        "## Question",
        question,
        "",
        "## Search Scope",
        f"- Profile: {profile}",
        f"- Providers: {', '.join(providers)}",
        f"- Queries: {len(queries)}",
        f"- Sources retained: {len(sources)}",
        f"- Evidence cards: {len(evidence)}",
        "",
        "## Query Plan",
        "",
        "| Intent | Query | Rationale |",
        "| --- | --- | --- |",
    ]
    for query in queries:
        lines.append(f"| `{md_cell(query.intent)}` | {md_cell(query.query)} | {md_cell(query.rationale)} |")
    lines.extend(
        [
            "",
            "## Ranked Similar Works",
            "",
            "| Rank | Source | Year | Venue | Score | Why it matched | Link |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for index, source in enumerate(sources[:15], 1):
        year = str(source.year or "")
        link = source_url(source)
        link_text = f"[link]({link})" if link else ""
        why = ", ".join(source.matches) if source.matches else "term overlap"
        lines.append(
            f"| {index} | `{source.source_id}` {md_cell(source.title)} | {year} | {md_cell(source.venue)} | {source.score} | {md_cell(why)} | {link_text} |"
        )
    lines.extend(
        [
            "",
            "## Evidence Cards",
        ]
    )
    for item in evidence:
        matched = ", ".join(item.get("matches") or [])
        lines.extend(
            [
                "",
                f"### `{item['evidence_id']}` / `{item['source_id']}`",
                f"- Confidence: {item['confidence']}",
                f"- Matched concepts: {matched or 'term overlap'}",
                f"- Locator: {item['source_locator']}",
                f"- Evidence: {item['evidence_text']}",
            ]
        )
    lines.extend(
        [
            "",
            "## How To Present This Search",
            "- Start with the Ranked Similar Works table for human reading.",
            "- Use Evidence Cards for audit trails and exact source identifiers.",
            "- Mention Query Plan when explaining why a refined search differs from a literal title search.",
            "",
            "## Caveats",
            "- Scores are deterministic heuristics for search triage, not truth labels.",
            "- Confirm high-stakes claims against the full paper before citing them.",
        ]
    )
    return "\n".join(lines) + "\n"


def inspect_bundle(path: Path) -> int:
    missing = [name for name in REQUIRED_BUNDLE_FILES if not (path / name).exists()]
    print(f"Bundle: {path}")
    if missing:
        print(f"Missing files: {', '.join(missing)}")
        return 1
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    print(f"Question: {manifest.get('question', '')}")
    print(f"Profile: {manifest.get('profile', '')}")
    print(f"Counts: {manifest.get('counts', {})}")
    print("Files: ok")
    return 0


def bundle_manifest(question: str, profile: str, created_at: str, counts: dict[str, int]) -> dict[str, Any]:
    return {
        "bundle_format_version": BUNDLE_FORMAT_VERSION,
        "question": question,
        "profile": profile,
        "created_at": created_at,
        "counts": counts,
        "files": BUNDLE_FILES,
    }


def parse_providers(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def provider_search(provider: str, query: QueryRecord, limit: int) -> tuple[list[SourceRecord], dict[str, Any]]:
    started = time.time()
    if provider not in SEARCHERS:
        raise ValueError(f"unsupported provider: {provider}")
    rows = SEARCHERS[provider](query.query, limit)
    return rows, {
        "timestamp": now_iso(),
        "provider": provider,
        "query": query.query,
        "status": "ok",
        "result_count": len(rows),
        "elapsed_seconds": round(time.time() - started, 3),
    }


def provider_error(provider: str, query: QueryRecord, exc: Exception) -> dict[str, Any]:
    return {
        "timestamp": now_iso(),
        "provider": provider,
        "query": query.query,
        "status": "error",
        "error": str(exc),
    }


def run_provider_queries(queries: list[QueryRecord], providers: list[str], limit: int) -> tuple[list[SourceRecord], list[dict[str, Any]]]:
    sources: list[SourceRecord] = []
    provenance: list[dict[str, Any]] = []
    for query in queries:
        for provider in providers:
            try:
                rows, event = provider_search(provider, query, limit)
                sources.extend(rows)
                provenance.append(event)
            except (urllib.error.URLError, TimeoutError, socket.timeout, ValueError, json.JSONDecodeError, ET.ParseError) as exc:
                provenance.append(provider_error(provider, query, exc))
    return sources, provenance


def write_bundle_outputs(
    out: Path,
    question: str,
    profile: str,
    providers: list[str],
    created_at: str,
    queries: list[QueryRecord],
    sources: list[SourceRecord],
    provenance: list[dict[str, Any]],
    max_evidence: int,
) -> list[dict[str, Any]]:
    evidence = evidence_rows(sources, min(max_evidence, len(sources)))
    append_jsonl(out / BUNDLE_FILES["sources"], [asdict(source) for source in sources])
    append_jsonl(out / BUNDLE_FILES["evidence"], evidence)
    append_jsonl(out / BUNDLE_FILES["provenance"], provenance)
    (out / BUNDLE_FILES["brief"]).write_text(render_brief(question, profile, providers, queries, sources, evidence), encoding="utf-8")
    write_json(
        out / "manifest.json",
        bundle_manifest(
            question,
            profile,
            created_at,
            {
                "queries": len(queries),
                "sources": len(sources),
                "evidence": len(evidence),
                "provenance": len(provenance),
            },
        ),
    )
    return evidence


def run_search(args: argparse.Namespace) -> int:
    providers = parse_providers(args.providers)
    queries = make_queries(args.question, args.profile, providers)
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    request = {
        "question": args.question,
        "profile": args.profile,
        "providers": providers,
        "max_results": args.max_results,
        "created_at": now_iso(),
    }
    write_json(out / BUNDLE_FILES["request"], request)
    append_jsonl(out / BUNDLE_FILES["queries"], [asdict(query) for query in queries])

    if args.plan_only:
        write_json(
            out / "manifest.json",
            bundle_manifest(args.question, args.profile, request["created_at"], {"queries": len(queries), "sources": 0}),
        )
        print(f"Planned {len(queries)} queries: {out}")
        return 0

    per_query_limit = max(1, min(args.max_results, 10))
    sources, provenance = run_provider_queries(queries, providers, per_query_limit)
    ranked = focus_ranked_sources(args.question, score_sources(args.question, dedupe_sources(sources)), args.max_results)
    write_bundle_outputs(out, args.question, args.profile, providers, request["created_at"], queries, ranked, provenance, args.max_evidence)
    print(f"Wrote deep web search bundle: {out}")
    return 0 if ranked else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run standalone academic deep web search.")
    sub = parser.add_subparsers(dest="command")

    search = sub.add_parser("search", help="Search academic providers and write a bundle")
    search.add_argument("question")
    search.add_argument("--out", default="./deep-web-search-bundle")
    search.add_argument("--profile", choices=sorted(PROFILE_EXPANSIONS), default="general")
    search.add_argument("--providers", default=",".join(DEFAULT_PROVIDERS), help="Comma-separated providers: arxiv,openalex")
    search.add_argument("--max-results", type=int, default=20)
    search.add_argument("--max-evidence", type=int, default=8)
    search.add_argument("--plan-only", action="store_true")
    search.set_defaults(func=run_search)

    inspect = sub.add_parser("inspect", help="Inspect a deep web search bundle")
    inspect.add_argument("bundle")
    inspect.set_defaults(func=lambda args: inspect_bundle(Path(args.bundle).expanduser().resolve()))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
