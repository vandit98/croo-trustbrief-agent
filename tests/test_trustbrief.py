import asyncio
import datetime as dt
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from trustbrief_agent.cap_provider import build_delivery_request, handle_negotiation_created, handle_order_paid
from trustbrief_agent.core import analyze_request, evaluate_claim, load_source
from trustbrief_agent.evidence_bundle import build_evidence_bundle
from trustbrief_agent.mock_cap_harness import run_mock_cap_flow


FIXED_NOW = dt.datetime(2026, 6, 13, 0, 0, tzinfo=dt.timezone.utc)


@dataclass
class FakeOrder:
    order_id: str
    negotiation_id: str


@dataclass
class FakeNegotiation:
    negotiation_id: str
    requirements: str


@dataclass
class FakeAcceptResult:
    order: FakeOrder


@dataclass
class FakeDeliverResult:
    tx_hash: str


@dataclass
class FakeEvent:
    negotiation_id: str = ""
    order_id: str = ""


class FakeDeliverableType:
    SCHEMA = "schema"
    TEXT = "text"


class FakeDeliverOrderRequest:
    def __init__(self, *, deliverable_type: str, deliverable_schema: str = "", deliverable_text: str = "") -> None:
        self.deliverable_type = deliverable_type
        self.deliverable_schema = deliverable_schema
        self.deliverable_text = deliverable_text


class FakeCapClient:
    def __init__(self, requirements: dict) -> None:
        self.negotiation = FakeNegotiation(
            negotiation_id="neg_test_001",
            requirements=json.dumps(requirements, sort_keys=True),
        )
        self.order = FakeOrder(order_id="ord_test_001", negotiation_id=self.negotiation.negotiation_id)
        self.accepted = []
        self.delivered = []

    async def accept_negotiation(self, negotiation_id: str) -> FakeAcceptResult:
        self.accepted.append(negotiation_id)
        return FakeAcceptResult(order=self.order)

    async def get_order(self, order_id: str) -> FakeOrder:
        self.assert_order_id(order_id)
        return self.order

    async def get_negotiation(self, negotiation_id: str) -> FakeNegotiation:
        if negotiation_id != self.negotiation.negotiation_id:
            raise ValueError("unexpected negotiation_id")
        return self.negotiation

    async def deliver_order(self, order_id: str, request: FakeDeliverOrderRequest) -> FakeDeliverResult:
        self.assert_order_id(order_id)
        self.delivered.append(request)
        return FakeDeliverResult(tx_hash="0xtestdeliver01")

    def assert_order_id(self, order_id: str) -> None:
        if order_id != self.order.order_id:
            raise ValueError("unexpected order_id")


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

    def test_build_delivery_request_supports_schema_and_text(self):
        report = analyze_request(
            {
                "task": "Verify claims.",
                "subject": "Delivery mode",
                "claims": [],
                "sources": [],
            },
            now=FIXED_NOW,
        )

        schema_request = build_delivery_request(report, "schema", FakeDeliverOrderRequest, FakeDeliverableType)
        text_request = build_delivery_request(report, "text", FakeDeliverOrderRequest, FakeDeliverableType)

        self.assertEqual(schema_request.deliverable_type, "schema")
        self.assertTrue(schema_request.deliverable_schema.startswith("{"))
        self.assertEqual(text_request.deliverable_type, "text")
        self.assertIn("\n", text_request.deliverable_text)

    def test_provider_handlers_accept_and_deliver(self):
        payload = {
            "task": "Verify claims.",
            "subject": "CAP proof",
            "claims": ["CAP supports settlement delivery."],
            "sources": [{"label": "fixture", "text": "CAP supports settlement delivery for agent services."}],
        }
        client = FakeCapClient(payload)

        accept_result = asyncio.run(
            handle_negotiation_created(client, FakeEvent(negotiation_id=client.negotiation.negotiation_id), auto_accept=True)
        )
        delivery = asyncio.run(
            handle_order_paid(
                client,
                FakeEvent(order_id=client.order.order_id),
                deliver_mode="schema",
                use_openai=False,
                deliver_order_request_cls=FakeDeliverOrderRequest,
                deliverable_type=FakeDeliverableType,
            )
        )

        self.assertEqual(accept_result.order.order_id, client.order.order_id)
        self.assertEqual(client.accepted, [client.negotiation.negotiation_id])
        self.assertEqual(len(client.delivered), 1)
        self.assertEqual(client.delivered[0].deliverable_type, "schema")
        self.assertRegex(delivery["report"]["proof"]["report_hash"], r"^[a-f0-9]{64}$")

    def test_mock_cap_flow_generates_judge_visible_transcript(self):
        transcript = asyncio.run(
            run_mock_cap_flow(
                {
                    "task": "Verify judge-facing CROO claims.",
                    "subject": "TrustBrief demo",
                    "claims": ["TrustBrief returns a report hash with evidence-backed claim assessments."],
                    "sources": [
                        {
                            "label": "fixture",
                            "text": "TrustBrief returns a report hash, evidence-backed claim assessments, and source hashes.",
                        }
                    ],
                }
            )
        )

        self.assertEqual(transcript["accepted_negotiations"], ["neg_mock_001"])
        self.assertEqual(transcript["delivery_mode"], "schema")
        self.assertIn("report_hash", transcript["report_summary"])
        self.assertGreater(transcript["delivered_preview"]["schema_bytes"], 0)

    def test_evidence_bundle_collects_consistent_offline_proof(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "test_demo_report.json"
            mock_path = Path(tmpdir) / "test_mock_cap_demo.json"
            report_path.write_text("{\"ok\":true}\n", encoding="utf-8")
            mock_path.write_text("{\"ok\":true}\n", encoding="utf-8")

            bundle = build_evidence_bundle(
                {
                    "task": "Verify judge-facing CROO claims.",
                    "subject": "TrustBrief bundle",
                    "claims": ["TrustBrief returns a report hash with evidence-backed claim assessments."],
                    "sources": [
                        {
                            "label": "fixture",
                            "text": "TrustBrief returns a report hash, evidence-backed claim assessments, and source hashes.",
                        }
                    ],
                },
                request_path=Path("examples/sample_request.json"),
                repo_root=Path(__file__).resolve().parents[1],
                analysis_now=FIXED_NOW,
                validation_results={
                    "tests": {
                        "command": "python3 -m unittest discover -s tests -p 'test_*.py'",
                        "exit_code": 0,
                        "passed": True,
                        "stdout_tail": ["Ran 8 tests in 0.057s", "OK"],
                        "stderr_tail": [],
                    }
                },
                generated_artifact_paths=[report_path, mock_path],
            )

        self.assertEqual(bundle["bundle_schema_version"], "1.0.0")
        self.assertEqual(bundle["repo_state"]["branch"], "main")
        self.assertTrue(bundle["repo_state"]["commit"])
        self.assertIn("service_schema", bundle["judge_assets"])
        self.assertEqual(bundle["validation"]["tests"]["exit_code"], 0)
        self.assertTrue(bundle["validation"]["tests"]["passed"])
        self.assertEqual(len(bundle["judge_assets"]["generated_artifact_hashes"]), 2)
        self.assertTrue(bundle["judge_assets"]["generated_artifact_hashes"][0]["path"].endswith("test_demo_report.json"))
        self.assertTrue(bundle["offline_proof"]["consistency_checks"]["report_hash_matches_transcript"])
        self.assertTrue(bundle["offline_proof"]["consistency_checks"]["source_bundle_hash_matches_transcript"])
        self.assertRegex(bundle["proof"]["bundle_hash"], r"^[a-f0-9]{64}$")


if __name__ == "__main__":
    unittest.main()
