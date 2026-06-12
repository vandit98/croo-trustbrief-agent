import datetime as dt
import unittest

from trustbrief_agent.core import analyze_request, evaluate_claim, load_source


FIXED_NOW = dt.datetime(2026, 6, 13, 0, 0, tzinfo=dt.timezone.utc)


class TrustBriefTests(unittest.TestCase):
    def test_claim_evaluation_marks_supported_and_unsupported(self):
        source = load_source(
            {
                "label": "fixture",
                "text": (
                    "CROO Agent Protocol, or CAP, supports order negotiation, payment escrow, "
                    "deliverable submission, and settlement for agent services."
                ),
            },
            "2026-06-13T00:00:00Z",
        )
        supported = evaluate_claim("CAP supports order negotiation and escrow settlement.", [source])
        unsupported = evaluate_claim("CAP automatically books airline tickets for every user.", [source])

        self.assertIn(supported["status"], {"supported", "partially_supported"})
        self.assertEqual(unsupported["status"], "unsupported")

    def test_report_contains_proof_and_source_ledger(self):
        report = analyze_request(
            {
                "task": "Verify claims.",
                "subject": "CROO service setup",
                "claims": ["The dashboard handles service registration."],
                "sources": [
                    {
                        "label": "docs fixture",
                        "text": "Service registration is created and managed through the Agent Store dashboard Configure page.",
                    }
                ],
            },
            now=FIXED_NOW,
        )

        self.assertEqual(report["report_schema_version"], "1.0.0")
        self.assertEqual(report["source_ledger"][0]["label"], "docs fixture")
        self.assertRegex(report["proof"]["report_hash"], r"^[a-f0-9]{64}$")
        self.assertIn(report["recommendation"], {"ready", "usable_with_caveats", "needs_review"})

    def test_report_hash_is_stable_for_same_inputs(self):
        payload = {
            "task": "Verify claims.",
            "subject": "Stability",
            "claims": ["A source hash is included."],
            "sources": [{"label": "fixture", "text": "The source hash is included in the source ledger."}],
        }
        first = analyze_request(payload, now=FIXED_NOW)
        second = analyze_request(payload, now=FIXED_NOW)
        self.assertEqual(first["proof"]["report_hash"], second["proof"]["report_hash"])

    def test_missing_named_entity_prevents_false_support(self):
        report = analyze_request(
            {
                "task": "Verify claims.",
                "subject": "CROO setup",
                "claims": ["TrustBrief can replace the CROO dashboard registration step automatically."],
                "sources": [
                    {
                        "label": "docs fixture",
                        "text": "The CROO dashboard registration step creates an Agent DID and API key.",
                    }
                ],
            },
            now=FIXED_NOW,
        )
        self.assertEqual(report["claim_assessments"][0]["status"], "unsupported")
        self.assertIn("trustbrief", report["claim_assessments"][0]["evidence"][0]["missing_critical_terms"])


if __name__ == "__main__":
    unittest.main()
