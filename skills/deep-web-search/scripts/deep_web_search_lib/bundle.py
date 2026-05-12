from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import BUNDLE_FILES, BUNDLE_FORMAT_VERSION, REQUIRED_BUNDLE_FILES, QueryRecord, SourceRecord, append_jsonl, write_json
from .ranking import evidence_rows, source_url


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
