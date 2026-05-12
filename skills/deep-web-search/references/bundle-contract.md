# Deep Web Search Bundle Contract

Standalone Deep Web Search writes a directory bundle that can be inspected, cited, and reused by another agent.

Current format version: `deep-web-search-1.0`

```text
deep-web-search-bundle/
  manifest.json
  request.json
  queries.jsonl
  sources.jsonl
  evidence.jsonl
  provenance.jsonl
  brief.md
```

## Files

- `manifest.json`: bundle metadata, format version, file map, and record counts.
- `request.json`: user question, selected profile, providers, and search limits.
- `queries.jsonl`: generated provider queries, intent labels, and rationales.
- `sources.jsonl`: ranked academic source records with deterministic scores and matched concepts.
- `evidence.jsonl`: evidence snippets derived from source metadata and abstracts, linked to `source_id`.
- `provenance.jsonl`: provider calls, result counts, timing, and errors.
- `brief.md`: human-readable presentation surface with Search Scope, Query Plan, Ranked Similar Works, Evidence Cards, and caveats.

## Stable Identifiers

Use `source_id` from `sources.jsonl` and `evidence_id` from `evidence.jsonl` when answering the user. Do not invent bibliographic fields that are absent from the bundle.

## Providers

The standalone script currently supports:

- `arxiv`
- `openalex`

Both work without API keys.
