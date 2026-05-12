# deep-web-search-skill

Standalone Deep Web Search skill for traceable academic and technical literature search.

This repository contains an installable Agent skill plus a small standard-library Python search script. It can run academic deep searches without API keys, package installation, or shell aliases.

## Layout

```text
deep-web-search-skill/
  skills/
    deep-web-search/
      SKILL.md
      references/
        bundle-contract.md
      scripts/
        deep_web_search.py
  tests/
    test_deep_web_search.py
  evals/
    evals.json
```

## What It Does

- Generates profile-aware academic search queries.
- Refines long "similar work" titles into mechanism-focused query plans.
- Searches arXiv and OpenAlex without API keys.
- Deduplicates, ranks, and writes traceable source/evidence records.
- Produces a presentation-ready `brief.md` plus JSON/JSONL audit records.

## Local Installation

Install by symlinking the skill folder into the Agent skill directory. Example:

```bash
ln -s /Users/jxtang/Desktop/CodeProjects/deep-web-search-skill/skills/deep-web-search \
  "$CODEX_HOME/skills/deep-web-search"
```

If the target Agent does not support symlinks, copy only `skills/deep-web-search/`.

## Operating Model

An Agent using this skill should:

1. Read `skills/deep-web-search/SKILL.md`.
2. Run `python3 skills/deep-web-search/scripts/deep_web_search.py search "$QUESTION" --out ./deep-web-search-bundle`.
3. Run `python3 skills/deep-web-search/scripts/deep_web_search.py inspect ./deep-web-search-bundle`.
4. Read the generated bundle files and cite `source_id` / `evidence_id` in follow-up work.
