---
name: deep-web-search
description: Use Deep Web Search for traceable academic and technical research. Trigger for scholarly sources, similar-work discovery, paper search, literature-review evidence, citation-backed decisions, source comparison, or an auditable research bundle with provenance.
---

# Deep Web Search

Use the bundled standalone script to turn a research question into an auditable search bundle. The script searches arXiv/OpenAlex, ranks sources, extracts evidence snippets, and writes a presentation-ready `brief.md`.

Do not use this skill as a general chat answer, memory system, final manuscript writer, or broad web crawler.

## Run

Resolve paths relative to this `SKILL.md` directory.

Preview/refine queries:

```bash
python3 scripts/deep_web_search.py search "$QUESTION" \
  --profile general \
  --plan-only \
  --out ./deep-web-search-bundle
```

Run search:

```bash
python3 scripts/deep_web_search.py search "$QUESTION" \
  --profile general \
  --out ./deep-web-search-bundle
```

Inspect before relying on results:

```bash
python3 scripts/deep_web_search.py inspect ./deep-web-search-bundle
```

Write bundles to the caller's workspace or explicit output path, not inside this skill directory.

## Profiles

- `general`: broad academic and technical literature.
- `biomol`: biomedical, biomolecular, protein design, structure prediction, benchmarks, reproducibility, and safety caveats.
- `agent_skills`: LLM agents, skill libraries, tool use, self-improvement, memory, reflection, evaluation, and governance.

Choose the narrowest matching profile. For similar-work requests, the script can refine long titles into mechanism-focused queries; for allosteric/domain-insertion topics it searches domain insertion, insertion-site prediction, synthetic allostery, and circular permutation.

## Read Results

Read in this order:

```text
brief.md
evidence.jsonl
sources.jsonl
provenance.jsonl
```

Use `brief.md` as the user-facing first pass: Search Scope, Query Plan, Ranked Similar Works, Evidence Cards, and caveats.

Use JSONL files for audit. Cite `source_id` and `evidence_id`; do not invent bibliographic fields missing from the bundle. If results are thin, say so and run a refined search.

## Limits

- Deterministic ranking only; no LLM triage.
- Metadata/abstract evidence only; no PDF full-text reading.
- Providers currently supported: `arxiv`, `openalex`.

Provider narrowing example:

```bash
python3 scripts/deep_web_search.py search "$QUESTION" \
  --providers arxiv,openalex \
  --out ./deep-web-search-bundle
```

Read `references/bundle-contract.md` only when exact output fields are needed.
