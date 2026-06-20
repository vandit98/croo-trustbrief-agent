import asyncio
import datetime as dt
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from trustbrief_agent.cap_provider import build_delivery_request, handle_negotiation_created, handle_order_paid
from trustbrief_agent.core import analyze_request, evaluate_claim, load_source
from trustbrief_agent.evidence_bundle import _build_artifact_freshness, build_evidence_bundle
from trustbrief_agent.mock_cap_harness import run_mock_cap_flow
from trustbrief_agent.requester_harness import build_requester_demo, validate_request_against_service_schema
from trustbrief_agent.submission_package import build_submission_package, render_submission_markdown


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
                public_repo_state={
                    "repository_url": "https://github.com/vandit98/croo-trustbrief-agent",
                    "default_branch": "main",
                    "visibility": "public",
                    "head_commit": "074f5813c83c5d1c8e5d33ec5e27b660423d6d70",
                    "verified_at": "2026-06-14T00:00:00Z",
                    "verification_source": "unit-test fixture",
                },
            )

        self.assertEqual(bundle["bundle_schema_version"], "1.0.0")
        self.assertEqual(bundle["repo_state"]["branch"], "main")
        self.assertTrue(bundle["repo_state"]["commit"])
        self.assertEqual(bundle["public_repo_state"]["default_branch"], "main")
        self.assertIn("service_schema", bundle["judge_assets"])
        self.assertEqual(bundle["validation"]["tests"]["exit_code"], 0)
        self.assertTrue(bundle["validation"]["tests"]["passed"])
        self.assertEqual(len(bundle["judge_assets"]["generated_artifact_hashes"]), 2)
        self.assertTrue(bundle["judge_assets"]["generated_artifact_hashes"][0]["path"].endswith("test_demo_report.json"))
        self.assertTrue(bundle["offline_proof"]["consistency_checks"]["report_hash_matches_transcript"])
        self.assertTrue(bundle["offline_proof"]["consistency_checks"]["source_bundle_hash_matches_transcript"])
        self.assertTrue(bundle["offline_proof"]["requester_demo"]["schema_validation"]["valid"])
        self.assertFalse(bundle["offline_proof"]["consistency_checks"]["local_commit_matches_public_head"])
        self.assertEqual(bundle["artifact_freshness"]["status"], "public_head_mismatch")
        self.assertTrue(bundle["artifact_freshness"]["regeneration_required"])
        self.assertRegex(bundle["proof"]["bundle_hash"], r"^[a-f0-9]{64}$")

    def test_artifact_freshness_flags_public_head_and_tracked_drift(self):
        fresh = _build_artifact_freshness(
            commit="abc123",
            status_lines=["?? research/planner_notes/latest.md"],
            tracked_status_lines=[],
            public_repo_state={"head_commit": "abc123"},
        )
        stale = _build_artifact_freshness(
            commit="abc123",
            status_lines=[],
            tracked_status_lines=[],
            public_repo_state={"head_commit": "def456"},
        )
        tracked_dirty = _build_artifact_freshness(
            commit="abc123",
            status_lines=[" M README.md"],
            tracked_status_lines=[" M README.md"],
            public_repo_state={"head_commit": "abc123"},
        )

        self.assertEqual(fresh["status"], "fresh_public_head")
        self.assertTrue(fresh["fresh_for_public_demo"])
        self.assertTrue(fresh["untracked_files_present"])
        self.assertFalse(fresh["tracked_files_dirty"])
        self.assertEqual(stale["status"], "public_head_mismatch")
        self.assertFalse(stale["fresh_for_public_demo"])
        self.assertEqual(tracked_dirty["status"], "tracked_files_dirty")
        self.assertFalse(tracked_dirty["fresh_for_public_demo"])

    def test_request_payload_validation_matches_service_schema(self):
        service_schema = json.loads(Path("service_schema.json").read_text(encoding="utf-8"))
        valid = validate_request_against_service_schema(
            {
                "task": "Verify claims.",
                "subject": "TrustBrief request",
                "claims": ["A claim"],
                "sources": [{"label": "fixture", "text": "A source"}],
            },
            service_schema,
        )
        invalid = validate_request_against_service_schema(
            {
                "task": "",
                "subject": "TrustBrief request",
                "claims": "A claim",
                "sources": [{"label": "fixture"}],
            },
            service_schema,
        )

        self.assertTrue(valid["valid"])
        self.assertFalse(valid["errors"])
        self.assertFalse(invalid["valid"])
        self.assertIn("missing required field: task", invalid["errors"])
        self.assertIn("claims must be array, got string", invalid["errors"])
        self.assertIn("sources[0] must include at least one of url, text, or path", invalid["errors"])

    def test_requester_demo_builds_offline_preview_and_live_readiness(self):
        packet = build_requester_demo(
            {
                "task": "Verify judge-facing CROO claims.",
                "subject": "TrustBrief requester harness",
                "claims": ["TrustBrief returns a report hash with evidence-backed claim assessments."],
                "sources": [
                    {
                        "label": "fixture",
                        "text": "TrustBrief returns a report hash, evidence-backed claim assessments, and source hashes.",
                    }
                ],
            },
            request_path=Path("examples/sample_request.json"),
        )

        self.assertEqual(packet["requester_demo_schema_version"], "1.0.0")
        self.assertTrue(packet["schema_validation"]["valid"])
        self.assertRegex(packet["offline_preview"]["report_summary"]["report_hash"], r"^[a-f0-9]{64}$")
        self.assertEqual(packet["offline_preview"]["mock_cap_summary"]["order_id"], "ord_mock_001")
        self.assertFalse(packet["live_order_readiness"]["ready_to_attempt"])
        self.assertFalse(packet["live_order_readiness"]["gate_checks"]["required_env_present"])
        self.assertTrue(packet["live_order_readiness"]["service_readiness"]["ready"])
        self.assertIn("CROO_API_URL", packet["live_order_readiness"]["required_env"])
        self.assertIn("proof_targets", packet["live_order_readiness"])
        self.assertEqual(packet["live_order_readiness"]["provider_start"]["command"], "python3.10 -m trustbrief_agent.cap_provider")

    def test_submission_package_builds_dorahacks_copy_from_bundle(self):
        bundle = _submission_bundle_fixture()
        package = build_submission_package(bundle, bundle_path=Path("outputs/judge_bundle.json"))

        self.assertEqual(package["package_schema_version"], "1.0.0")
        self.assertEqual(package["dorahacks_buidl_copy"]["project_name"], "TrustBrief CAP Verifier")
        self.assertEqual(package["dorahacks_buidl_copy"]["live_proof_status"], "blocked_by_credentials")
        self.assertTrue(package["source_bundle"]["fresh_for_public_demo"])
        self.assertEqual(package["source_hash_block"]["public_head_commit"], "abc123")
        self.assertTrue(package["source_hash_block"]["tests_passed"])
        self.assertIn("paid_order_chain", package["credentialed_live_proof_slot"]["proof_targets"])
        self.assertFalse(package["credentialed_live_proof_slot"]["ready_to_attempt"])

    def test_submission_package_markdown_preserves_live_blockers(self):
        package = build_submission_package(_submission_bundle_fixture())
        rendered = render_submission_markdown(package)

        self.assertIn("# DoraHacks Demo Package", rendered)
        self.assertIn("TrustBrief CAP Verifier", rendered)
        self.assertIn("Bundle freshness: fresh_public_head (fresh_for_public_demo=True)", rendered)
        self.assertIn("Missing CROO runtime env vars", rendered)
        self.assertIn("paid_order_chain", rendered)
        self.assertNotIn("live paid order complete", rendered.lower())


def _submission_bundle_fixture():
    return {
        "generated_at": "2026-06-20T00:00:00Z",
        "repo_state": {
            "commit": "abc123",
            "remote_origin": "https://github.com/vandit98/croo-trustbrief-agent.git",
        },
        "public_repo_state": {
            "repository_url": "https://github.com/vandit98/croo-trustbrief-agent",
            "head_commit": "abc123",
            "head_commit_url": "https://github.com/vandit98/croo-trustbrief-agent/commit/abc123",
            "verified_at": "2026-06-20T00:00:00Z",
        },
        "artifact_freshness": {
            "status": "fresh_public_head",
            "fresh_for_public_demo": True,
        },
        "proof": {
            "bundle_hash": "b" * 64,
            "report_hash": "r" * 64,
            "mock_tx_hash": "0xmockdelivery",
        },
        "judge_assets": {
            "service_schema": {
                "agent_store_listing": {
                    "agent_name": "TrustBrief CAP Verifier",
                    "tracks": ["Research & Intelligence Agents", "Data & Verification Agents"],
                },
                "service": {
                    "service_name": "Verified Research Brief",
                    "price_usdc": 1.0,
                    "sla_minutes": 20,
                    "deliverable_type": "schema",
                },
            },
            "key_asset_hashes": [
                {"path": "README.md", "sha256": "1" * 64},
                {"path": "service_schema.json", "sha256": "2" * 64},
            ],
        },
        "validation": {
            "tests": {
                "passed": True,
            },
        },
        "offline_proof": {
            "requester_demo": {
                "request_fingerprint": {
                    "input_hash": "a" * 64,
                },
                "offline_preview": {
                    "report_summary": {
                        "report_hash": "r" * 64,
                    },
                    "mock_cap_summary": {
                        "order_id": "ord_mock_001",
                        "tx_hash": "0xmockdelivery",
                    },
                },
                "live_order_readiness": {
                    "ready_to_attempt": False,
                    "gate_checks": {
                        "request_schema_valid": True,
                        "service_listing_ready": True,
                        "required_env_present": False,
                    },
                    "required_env": {
                        "CROO_API_URL": False,
                        "CROO_WS_URL": False,
                        "CROO_SDK_KEY": False,
                    },
                    "blocked_reasons": [
                        "Missing CROO runtime env vars: CROO_API_URL, CROO_WS_URL, CROO_SDK_KEY.",
                    ],
                    "proof_targets": [
                        {"artifact": "agent_store_listing"},
                        {"artifact": "paid_order_chain"},
                        {"artifact": "delivered_report_hash"},
                    ],
                    "manual_steps": [
                        "Register the provider in the CROO Agent Store dashboard and paste service_schema.json.",
                    ],
                },
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
