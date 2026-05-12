from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from .bundle import bundle_manifest, inspect_bundle, write_bundle_outputs
from .models import BUNDLE_FILES, DEFAULT_PROVIDERS, DEFAULT_WORKERS, PROFILE_EXPANSIONS, append_jsonl, now_iso, write_json
from .providers import run_provider_queries
from .queries import make_queries
from .ranking import dedupe_sources, focus_ranked_sources, score_sources


def parse_providers(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def progress_line(enabled: bool, message: str) -> None:
    if enabled:
        print(message, file=sys.stderr, flush=True)


def short_query(value: str, limit: int = 72) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def run_search(args: argparse.Namespace) -> int:
    providers = parse_providers(args.providers)
    queries = make_queries(args.question, args.profile, providers)
    workers = max(1, args.workers)
    progress_enabled = bool(getattr(args, "progress", False))
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    total_tasks = len(queries) * len(providers)
    progress_line(progress_enabled, f"[plan] {len(queries)} queries x {len(providers)} providers workers={workers}")
    for index, query in enumerate(queries, 1):
        progress_line(progress_enabled, f"[plan] q{index} {query.intent}: {short_query(query.query)}")

    request = {
        "question": args.question,
        "profile": args.profile,
        "providers": providers,
        "max_results": args.max_results,
        "workers": workers,
        "created_at": now_iso(),
    }
    write_json(out / BUNDLE_FILES["request"], request)
    append_jsonl(out / BUNDLE_FILES["queries"], [asdict(query) for query in queries])

    if args.plan_only:
        write_json(
            out / "manifest.json",
            bundle_manifest(args.question, args.profile, request["created_at"], {"queries": len(queries), "sources": 0}),
        )
        progress_line(progress_enabled, f"[bundle] wrote plan-only bundle: {out}")
        print(f"Planned {len(queries)} queries: {out}")
        return 0

    per_query_limit = max(1, min(args.max_results, 10))
    progress_line(progress_enabled, f"[search] start tasks={total_tasks} per_query_limit={per_query_limit}")
    completed_tasks = 0

    def report_provider_result(_index: int, rows: list[object], event: dict[str, object]) -> None:
        nonlocal completed_tasks
        completed_tasks += 1
        provider = event.get("provider", "unknown")
        query = short_query(str(event.get("query", "")), limit=52)
        if event.get("status") == "ok":
            count = event.get("result_count", 0)
            elapsed = event.get("elapsed_seconds", "?")
            progress_line(progress_enabled, f"[search] {completed_tasks}/{total_tasks} {provider} ok results={count} elapsed={elapsed}s query={query}")
        else:
            error = short_query(str(event.get("error", "")), limit=56)
            progress_line(progress_enabled, f"[search] {completed_tasks}/{total_tasks} {provider} error={error} query={query}")

    sources, provenance = run_provider_queries(
        queries,
        providers,
        per_query_limit,
        workers=workers,
        progress=report_provider_result if progress_enabled else None,
    )
    deduped = dedupe_sources(sources)
    scored = score_sources(args.question, deduped)
    ranked = focus_ranked_sources(args.question, scored, args.max_results)
    progress_line(progress_enabled, f"[rank] raw={len(sources)} deduped={len(deduped)} retained={len(ranked)}")
    evidence = write_bundle_outputs(out, args.question, args.profile, providers, request["created_at"], queries, ranked, provenance, args.max_evidence)
    progress_line(progress_enabled, f"[bundle] wrote sources={len(ranked)} evidence={len(evidence)} provenance={len(provenance)} out={out}")
    print(f"Wrote deep web search bundle: {out}")
    return 0 if ranked else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run standalone academic deep web search.")
    sub = parser.add_subparsers(dest="command")

    search = sub.add_parser("search", help="Search academic providers and write a bundle")
    search.add_argument("question")
    search.add_argument("--out", default="./deep-web-search-bundle")
    search.add_argument("--profile", choices=sorted(PROFILE_EXPANSIONS), default="general")
    search.add_argument(
        "--providers",
        default=",".join(DEFAULT_PROVIDERS),
        help="Comma-separated providers: tavily,semantic_scholar,pubmed,openalex,arxiv",
    )
    search.add_argument("--max-results", type=int, default=20)
    search.add_argument("--max-evidence", type=int, default=8)
    search.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Parallel provider request workers; use 1 for serial execution")
    search.add_argument("--progress", action="store_true", help="Print live search progress to stderr for agent harness displays")
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
