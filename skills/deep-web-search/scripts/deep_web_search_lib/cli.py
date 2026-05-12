from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from .bundle import bundle_manifest, inspect_bundle, write_bundle_outputs
from .models import BUNDLE_FILES, DEFAULT_PROVIDERS, DEFAULT_WORKERS, PROFILE_EXPANSIONS, append_jsonl, now_iso, write_json
from .providers import run_provider_queries
from .queries import make_queries
from .ranking import dedupe_sources, focus_ranked_sources, score_sources


def parse_providers(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def run_search(args: argparse.Namespace) -> int:
    providers = parse_providers(args.providers)
    queries = make_queries(args.question, args.profile, providers)
    workers = max(1, args.workers)
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

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
        print(f"Planned {len(queries)} queries: {out}")
        return 0

    per_query_limit = max(1, min(args.max_results, 10))
    sources, provenance = run_provider_queries(queries, providers, per_query_limit, workers=workers)
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
    search.add_argument(
        "--providers",
        default=",".join(DEFAULT_PROVIDERS),
        help="Comma-separated providers: tavily,semantic_scholar,pubmed,openalex,arxiv",
    )
    search.add_argument("--max-results", type=int, default=20)
    search.add_argument("--max-evidence", type=int, default=8)
    search.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Parallel provider request workers; use 1 for serial execution")
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
