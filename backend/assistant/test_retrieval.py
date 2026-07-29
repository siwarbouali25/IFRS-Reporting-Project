from django.test import SimpleTestCase

from .retrieval import (
    chunk_markdown,
    rank_chunks,
)


class FinalMarkdownRetrievalTests(
    SimpleTestCase
):
    SAMPLE = """
# IFRS S1/S2 Report

## Governance

The Board Risk Committee oversees climate-related risks and approves the
institution's sustainability risk appetite.

## Strategy

### Transition planning

The bank's transition plan prioritizes financed-emissions reduction in
high-carbon sectors and engagement with major counterparties.

### Physical resilience

Flood and heat-stress scenarios are considered in location-level exposure
assessment.

## Metrics and Targets

| Metric | Value |
|---|---:|
| Scope 1 emissions | 120 tCO2e |
| Scope 2 market-based emissions | 340 tCO2e |
"""

    def test_heading_aware_chunking(self):
        chunks = chunk_markdown(
            self.SAMPLE,
            artifact_id="A1",
            max_chars=300,
            overlap_chars=20,
        )

        self.assertGreaterEqual(
            len(chunks),
            4,
        )
        self.assertTrue(
            any(
                "Strategy > Transition planning"
                == chunk.section_path
                for chunk in chunks
            )
        )

    def test_transition_plan_query_finds_strategy(self):
        chunks = chunk_markdown(
            self.SAMPLE,
            artifact_id="A1",
            max_chars=300,
            overlap_chars=20,
        )
        results = rank_chunks(
            "How does the report describe its transition plan?",
            chunks,
            top_k=3,
        )

        self.assertTrue(results)
        self.assertIn(
            "Transition planning",
            results[0]["chunk"].section_path,
        )

    def test_governance_query_finds_board_oversight(self):
        chunks = chunk_markdown(
            self.SAMPLE,
            artifact_id="A1",
            max_chars=300,
            overlap_chars=20,
        )
        results = rank_chunks(
            "Who oversees climate risks?",
            chunks,
            top_k=3,
        )

        self.assertTrue(results)
        self.assertIn(
            "Governance",
            results[0]["chunk"].section_path,
        )

    def test_unrelated_query_returns_no_strong_hit(self):
        chunks = chunk_markdown(
            self.SAMPLE,
            artifact_id="A1",
            max_chars=300,
            overlap_chars=20,
        )
        results = rank_chunks(
            "medieval castle architecture",
            chunks,
            top_k=3,
        )

        self.assertEqual(
            results,
            [],
        )
