import unittest
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "skills" / "deep-web-search" / "scripts" / "deep_web_search.py"
SPEC = importlib.util.spec_from_file_location("deep_web_search", SCRIPT_PATH)
deep_web_search = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["deep_web_search"] = deep_web_search
SPEC.loader.exec_module(deep_web_search)


class DeepWebSearchTests(unittest.TestCase):
    def test_make_queries_uses_profile_expansions(self):
        queries = deep_web_search.make_queries("agent skill libraries", "agent_skills", ["arxiv"])

        self.assertEqual(queries[0].query, "agent skill libraries")
        self.assertEqual(len(queries), 5)
        self.assertTrue(all(query.provider_targets == ["arxiv"] for query in queries))

    def test_allosteric_switch_query_uses_mechanism_refinements(self):
        queries = deep_web_search.make_queries(
            "Rational engineering of allosteric protein switches by in silico prediction of domain insertion sites similar work",
            "biomol",
            ["arxiv", "openalex"],
        )

        query_text = [query.query for query in queries]
        intents = [query.intent for query in queries]
        self.assertIn("mechanism:domain_insertion_switches", intents)
        self.assertIn("mechanism:site_prediction", intents)
        self.assertIn("mechanism:circular_permutation", intents)
        self.assertNotIn(query_text[0] + " binder design", query_text)

    def test_dedupe_and_score_sources(self):
        sources = [
            deep_web_search.SourceRecord(source_id="a", title="LLM agent skill libraries", provider="arxiv", year=2026),
            deep_web_search.SourceRecord(source_id="b", title="LLM agent skill libraries", provider="openalex", year=2026),
            deep_web_search.SourceRecord(source_id="c", title="Unrelated topic", provider="openalex", year=2010),
        ]

        ranked = deep_web_search.score_sources("LLM agent skill libraries", deep_web_search.dedupe_sources(sources))

        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0].title, "LLM agent skill libraries")
        self.assertGreater(ranked[0].score, ranked[1].score)

    def test_render_brief_includes_presentation_sections(self):
        queries = deep_web_search.make_queries("domain insertion allosteric protein switches", "biomol", ["openalex"])
        sources = deep_web_search.score_sources(
            "domain insertion allosteric protein switches",
            [
                deep_web_search.SourceRecord(
                    source_id="src1",
                    title="Domain insertion allosteric protein switch",
                    provider="openalex",
                    abstract="A biosensor built by domain insertion and synthetic allostery.",
                    year=2025,
                    venue="Example Journal",
                    doi="10.example/test",
                )
            ],
        )
        evidence = deep_web_search.evidence_rows(sources, 1)
        brief = deep_web_search.render_brief("domain insertion allosteric protein switches", "biomol", ["openalex"], queries, sources, evidence)

        self.assertIn("## Query Plan", brief)
        self.assertIn("## Ranked Similar Works", brief)
        self.assertIn("## Evidence Cards", brief)
        self.assertIn("Why it matched", brief)

    def test_focus_ranked_sources_prefers_multi_concept_matches(self):
        sources = [
            deep_web_search.SourceRecord(source_id="a", title="Domain insertion protein switch biosensor", provider="openalex", matches=["domain insertion", "switch behavior", "biosensor"], score=0.7),
            deep_web_search.SourceRecord(source_id="b", title="Generic allosteric drug review", provider="openalex", matches=["allostery/allosteric"], score=0.6),
            deep_web_search.SourceRecord(source_id="c", title="Synthetic allostery protein switch", provider="openalex", matches=["allostery/allosteric", "switch behavior"], score=0.5),
            deep_web_search.SourceRecord(source_id="d", title="Circular permutation biosensor", provider="openalex", matches=["circular permutation", "biosensor"], score=0.4),
            deep_web_search.SourceRecord(source_id="e", title="Domain recombination switch", provider="openalex", matches=["domain recombination", "switch behavior"], score=0.3),
        ]

        focused = deep_web_search.focus_ranked_sources("allosteric protein switch domain insertion", sources, 5)

        self.assertEqual([source.source_id for source in focused], ["a", "c", "d", "e"])

    def test_parse_providers_discards_empty_parts(self):
        self.assertEqual(deep_web_search.parse_providers("arxiv, openalex,, "), ["arxiv", "openalex"])

    def test_run_provider_queries_parallel_preserves_task_order(self):
        def fake_a(query, limit):
            return [deep_web_search.SourceRecord(source_id=f"a-{query}", title=query, provider="fake_a")]

        def fake_b(query, limit):
            return [deep_web_search.SourceRecord(source_id=f"b-{query}", title=query, provider="fake_b")]

        queries = [
            deep_web_search.QueryRecord("q1", "primary", ["fake_a", "fake_b"]),
            deep_web_search.QueryRecord("q2", "primary", ["fake_a", "fake_b"]),
        ]
        with patch.dict(deep_web_search.SEARCHERS, {"fake_a": fake_a, "fake_b": fake_b}, clear=True):
            sources, provenance = deep_web_search.run_provider_queries(queries, ["fake_a", "fake_b"], 1, workers=2)

        self.assertEqual([source.source_id for source in sources], ["a-q1", "b-q1", "a-q2", "b-q2"])
        self.assertEqual(
            [(event["provider"], event["query"], event["status"]) for event in provenance],
            [("fake_a", "q1", "ok"), ("fake_b", "q1", "ok"), ("fake_a", "q2", "ok"), ("fake_b", "q2", "ok")],
        )

    def test_run_provider_queries_reports_progress(self):
        def fake_search(query, limit):
            return [deep_web_search.SourceRecord(source_id=f"src-{query}", title=query, provider="fake")]

        queries = [deep_web_search.QueryRecord("q1", "primary", ["fake"])]
        events = []
        with patch.dict(deep_web_search.SEARCHERS, {"fake": fake_search}, clear=True):
            deep_web_search.run_provider_queries(queries, ["fake"], 1, workers=1, progress=lambda index, rows, event: events.append((index, len(rows), event["status"])))

        self.assertEqual(events, [(0, 1, "ok")])

    def test_semantic_scholar_rate_limit_waits_between_requests(self):
        now = {"value": 10.0}
        sleeps = []

        def fake_monotonic():
            return now["value"]

        def fake_sleep(seconds):
            sleeps.append(seconds)
            now["value"] += seconds

        deep_web_search.PROVIDER_NEXT_ALLOWED_AT.clear()
        with patch.object(deep_web_search.time, "monotonic", fake_monotonic):
            with patch.object(deep_web_search.time, "sleep", fake_sleep):
                deep_web_search.wait_for_provider_rate_limit("semantic_scholar")
                deep_web_search.wait_for_provider_rate_limit("semantic_scholar")

        self.assertEqual(sleeps, [1.0])
        self.assertEqual(deep_web_search.PROVIDER_NEXT_ALLOWED_AT["semantic_scholar"], 12.0)
        deep_web_search.PROVIDER_NEXT_ALLOWED_AT.clear()

    def test_default_providers_include_key_backed_sources(self):
        self.assertEqual(
            deep_web_search.DEFAULT_PROVIDERS,
            ["tavily", "semantic_scholar", "pubmed", "openalex", "arxiv"],
        )

    def test_tavily_requires_api_key(self):
        with patch.dict(deep_web_search.os.environ, {"TAVILY_API_KEY": ""}, clear=True):
            with self.assertRaises(RuntimeError):
                deep_web_search.search_tavily("protein design", 1)

    def test_tavily_normalizes_web_results(self):
        payload = {"results": [{"url": "https://example.com/a", "title": "Example A", "content": "Useful web evidence."}]}
        with patch.dict(deep_web_search.os.environ, {"TAVILY_API_KEY": "test"}, clear=True):
            with patch.object(deep_web_search.providers, "post_json", return_value=payload):
                rows = deep_web_search.search_tavily("protein design", 1)

        self.assertEqual(rows[0].provider, "tavily")
        self.assertEqual(rows[0].source_type, "web")
        self.assertEqual(rows[0].snippet, "Useful web evidence.")

    def test_semantic_scholar_normalizes_papers(self):
        payload = {
            "data": [
                {
                    "paperId": "abc",
                    "url": "https://www.semanticscholar.org/paper/abc",
                    "title": "Semantic Scholar Paper",
                    "abstract": "Paper abstract.",
                    "authors": [{"name": "Ada Lovelace"}],
                    "year": 2025,
                    "venue": "Example Venue",
                    "citationCount": 12,
                    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                    "externalIds": {"DOI": "10.example/s2", "PubMed": "123", "ArXiv": "2501.00001"},
                    "fieldsOfStudy": ["Computer Science"],
                    "tldr": {"text": "Short summary."},
                }
            ]
        }
        with patch.object(deep_web_search.providers, "fetch_json", return_value=payload):
            rows = deep_web_search.search_semantic_scholar("agent skills", 1)

        self.assertEqual(rows[0].provider, "semantic_scholar")
        self.assertEqual(rows[0].semantic_scholar_id, "abc")
        self.assertEqual(rows[0].doi, "10.example/s2")
        self.assertEqual(rows[0].snippet, "Short summary.")

    def test_pubmed_parser_normalizes_articles(self):
        xml = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>123</PMID>
      <Article>
        <ArticleTitle>PubMed Paper</ArticleTitle>
        <Abstract><AbstractText Label="Background">Useful biomedical evidence.</AbstractText></Abstract>
        <Journal><Title>Example Journal</Title><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
        <AuthorList><Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName></Author></AuthorList>
      </Article>
    </MedlineCitation>
    <PubmedData><ArticleIdList><ArticleId IdType="doi">10.example/pubmed</ArticleId></ArticleIdList></PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""
        rows = deep_web_search.parse_pubmed_articles(xml)

        self.assertEqual(rows[0]["pmid"], "123")
        self.assertEqual(rows[0]["title"], "PubMed Paper")
        self.assertEqual(rows[0]["year"], 2024)
        self.assertEqual(rows[0]["doi"], "10.example/pubmed")

    def test_bundle_manifest_uses_canonical_file_map(self):
        manifest = deep_web_search.bundle_manifest("question", "general", "2026-01-01T00:00:00+00:00", {"queries": 1})

        self.assertEqual(manifest["bundle_format_version"], "deep-web-search-1.0")
        self.assertEqual(manifest["files"]["brief"], "brief.md")
        self.assertEqual(manifest["counts"]["queries"], 1)


if __name__ == "__main__":
    unittest.main()
