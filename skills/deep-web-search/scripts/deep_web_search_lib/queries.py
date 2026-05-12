from __future__ import annotations

from .models import PROFILE_EXPANSIONS, QueryRecord, slug


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
