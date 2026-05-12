import unittest
import importlib.util
import sys
from pathlib import Path


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

    def test_bundle_manifest_uses_canonical_file_map(self):
        manifest = deep_web_search.bundle_manifest("question", "general", "2026-01-01T00:00:00+00:00", {"queries": 1})

        self.assertEqual(manifest["bundle_format_version"], "deep-web-search-1.0")
        self.assertEqual(manifest["files"]["brief"], "brief.md")
        self.assertEqual(manifest["counts"]["queries"], 1)


if __name__ == "__main__":
    unittest.main()
