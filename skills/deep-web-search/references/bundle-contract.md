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

- `tavily`
- `semantic_scholar`
- `pubmed`
- `openalex`
- `arxiv`

Provider configuration:

- `tavily` requires `TAVILY_API_KEY`; `TAVILY_BASE_URL` is optional.
- `semantic_scholar` can use `S2_API_KEY` or `Semantic_Search_API_KEY`; keys are optional but recommended.
- `pubmed` can use `NCBI_EMAIL` and `NCBI_API_KEY`; email is recommended and the API key is optional.
- `openalex` can use `OPENALEX_EMAIL`; it is optional.
- `arxiv` does not use an API key.

Provider requests may run concurrently via `--workers`; Semantic Scholar requests are limited to one request per second. Output files remain deterministic because records are written in query/provider task order.
