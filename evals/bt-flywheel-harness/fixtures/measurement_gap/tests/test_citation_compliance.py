import unittest

from scorers.citation_compliance import score_citation_compliance


class CitationComplianceTests(unittest.TestCase):
    def test_scores_answer_with_source(self):
        self.assertEqual(
            score_citation_compliance("Use the escalation policy. Source: handbook."),
            1.0,
        )

    def test_fails_answer_without_source(self):
        self.assertEqual(
            score_citation_compliance("Use the escalation policy."),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
