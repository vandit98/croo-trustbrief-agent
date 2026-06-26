from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _load_json(path: Path) -> Dict[str, Any]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("{} must decode to a JSON object".format(path))
    return decoded


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_dict(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def _proof_target_names(readiness: Dict[str, Any]) -> List[str]:
    targets = readiness.get("proof_targets", [])
    if not isinstance(targets, list):
        return []
    names = []
    for item in targets:
        if isinstance(item, dict) and item.get("artifact"):
            names.append(str(item["artifact"]))
    return names


def _key_asset_lines(assets: Iterable[Dict[str, Any]]) -> List[str]:
    lines = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        path = asset.get("path", "")
        sha = asset.get("sha256", "")
        if path and sha:
            lines.append("{}: {}".format(path, sha))
    return lines


def build_submission_package(bundle: Dict[str, Any], *, bundle_path: Optional[Path] = None) -> Dict[str, Any]:
    judge_assets = _require_dict(bundle, "judge_assets")
    service_schema = _require_dict(judge_assets, "service_schema")
    listing = _require_dict(service_schema, "agent_store_listing")
    service = _require_dict(service_schema, "service")
    public_repo_state = _require_dict(bundle, "public_repo_state")
    repo_state = _require_dict(bundle, "repo_state")
    freshness = _require_dict(bundle, "artifact_freshness")
    proof = _require_dict(bundle, "proof")
    offline_proof = _require_dict(bundle, "offline_proof")
    requester_demo = _require_dict(offline_proof, "requester_demo")
    buyer_composability = _require_dict(offline_proof, "buyer_composability")
    live_commerce_evidence = _require_dict(offline_proof, "live_commerce_evidence")
    buyer_correlation = _require_dict(buyer_composability, "correlation")
    buyer_decision = _require_dict(buyer_composability, "downstream_decision")
    buyer_actors = _require_dict(buyer_composability, "actors")
    live_manifest_proof = _require_dict(live_commerce_evidence, "proof")
    payment_authorization = _require_dict(live_commerce_evidence, "payment_authorization")
    hash_comparison = _require_dict(live_commerce_evidence, "hash_comparison")
    tap_identity = _require_dict(live_commerce_evidence, "tap_style_identity_intent")
    readiness = _require_dict(requester_demo, "live_order_readiness")
    gate_checks = _require_dict(readiness, "gate_checks")
    required_env = _require_dict(readiness, "required_env")
    request_fingerprint = _require_dict(requester_demo, "request_fingerprint")
    offline_preview = _require_dict(requester_demo, "offline_preview")
    report_summary = _require_dict(offline_preview, "report_summary")
    mock_cap_summary = _require_dict(offline_preview, "mock_cap_summary")
    validation = _require_dict(bundle, "validation")
    test_result = _require_dict(validation, "tests")

    repo_url = public_repo_state.get("repository_url") or repo_state.get("remote_origin", "")
    tracks = listing.get("tracks", [])
    if not isinstance(tracks, list):
        tracks = []

    blocked_reasons = readiness.get("blocked_reasons", [])
    if not isinstance(blocked_reasons, list):
        blocked_reasons = []

    package = {
        "package_schema_version": "1.0.0",
        "source_bundle": {
            "path": str(bundle_path) if bundle_path else "",
            "generated_at": bundle.get("generated_at", ""),
            "freshness_status": freshness.get("status", ""),
            "fresh_for_public_demo": freshness.get("fresh_for_public_demo", False),
        },
        "dorahacks_buidl_copy": {
            "project_name": listing.get("agent_name", "TrustBrief CAP Verifier"),
            "one_liner": (
                "Paid CROO Agent Store verification service that returns claim-level due-diligence briefs "
                "with source hashes, risk flags, and CAP schema delivery."
            ),
            "tracks": tracks,
            "problem": (
                "Agents can spend money or trust marketplace services before checking the evidence behind a claim. "
                "Plain summaries are hard for another agent or judge to audit."
            ),
            "solution": (
                "TrustBrief accepts a task, subject, claims, and sources, then returns structured JSON with "
                "claim assessments, evidence snippets, SHA-256 source provenance, risk flags, and a stable report hash."
            ),
            "croo_integration": (
                "The live provider uses CROO AgentClient handlers for NEGOTIATION_CREATED and ORDER_PAID, accepts "
                "the negotiation, generates the report, and delivers a schema payload through CAP."
            ),
            "repository_url": repo_url,
            "demo_command": (
                "python3 -m trustbrief_agent.evidence_bundle examples/sample_request.json "
                "--report-output outputs/demo_report.json "
                "--mock-output outputs/mock_cap_demo.json "
                "--requester-output outputs/requester_demo.json "
                "--buyer-output outputs/buyer_composability_demo.json "
                "--live-commerce-output outputs/live_commerce_evidence.json "
                "--output outputs/judge_bundle.json"
            ),
            "live_proof_status": "blocked_by_credentials" if blocked_reasons else "ready_to_attempt",
            "live_commerce_manifest_status": live_commerce_evidence.get("status", ""),
        },
        "five_minute_runbook": [
            {
                "time": "0:00-0:30",
                "screen": "Public GitHub repo and README",
                "show": "Project name, MIT license, track fit, and the one-command offline demo.",
            },
            {
                "time": "0:30-1:15",
                "screen": "service_schema.json",
                "show": "Agent Store listing copy, 1 USDC price, 20 minute SLA, schema requirements, and schema deliverable.",
            },
            {
                "time": "1:15-2:20",
                "screen": "outputs/judge_bundle.json",
                "show": "Fresh public-head status, unit-test pass result, bundle hash, report hash, and generated artifact hashes.",
            },
            {
                "time": "2:20-3:20",
                "screen": "outputs/mock_cap_demo.json and trustbrief_agent/cap_provider.py",
                "show": "Negotiation acceptance, paid-order delivery path, mock order IDs, and the live SDK handler code.",
            },
            {
                "time": "3:20-4:20",
                "screen": "outputs/demo_report.json",
                "show": "Claim assessments, source ledger, risk flags, recommendation, and report hash.",
            },
            {
                "time": "4:20-5:00",
                "screen": "outputs/requester_demo.json, outputs/buyer_composability_demo.json, and outputs/live_commerce_evidence.json",
                "show": "Live-order gate checks, buyer-agent correlation ID, payment authorization slots, CAP lifecycle IDs, and exact live proof fields.",
            },
        ],
        "screenshot_checklist": [
            {
                "artifact": "public_repo",
                "capture": "Repo URL, README, MIT license, and latest public commit.",
                "status": "ready" if repo_url else "missing_public_repo_url",
            },
            {
                "artifact": "fresh_judge_bundle",
                "capture": "artifact_freshness.status, fresh_for_public_demo, bundle_hash, and report_hash.",
                "status": "ready" if freshness.get("fresh_for_public_demo") else "regenerate_before_demo",
            },
            {
                "artifact": "service_schema",
                "capture": "Agent name, service name, price, SLA, requirements schema, and deliverable schema.",
                "status": "ready" if service.get("service_name") and service.get("price_usdc") else "incomplete_schema",
            },
            {
                "artifact": "cap_lifecycle",
                "capture": "Mock negotiation_id, order_id, tx_hash, and provider handler code.",
                "status": "ready" if mock_cap_summary.get("order_id") else "missing_mock_transcript",
            },
            {
                "artifact": "live_order_placeholder",
                "capture": "Agent Store listing URL, provider-online log, real negotiation_id, order_id, tx_hash, and delivered report hash.",
                "status": "blocked_by_credentials" if blocked_reasons else "ready_to_capture",
            },
            {
                "artifact": "a2a_buyer_composability",
                "capture": "Correlation ID, TrustBrief report hash, buyer decision, and reserved live CAP/payment fields.",
                "status": "ready" if buyer_correlation.get("correlation_id") else "missing_buyer_packet",
            },
            {
                "artifact": "live_commerce_evidence_manifest",
                "capture": "Payment authorization checklist, CAP lifecycle slots, x402 payment states, TAP identity/intent fields, and hash comparison rule.",
                "status": "ready" if live_manifest_proof.get("manifest_hash") else "missing_live_manifest",
            },
        ],
        "judge_demo_capture_plan": {
            "recording_goal": (
                "Record a judge-ready offline demo that sells TrustBrief as paid pre-spend verification, "
                "not just generic A2A or payment plumbing."
            ),
            "positioning": [
                "Lead with the buyer problem: an agent should verify evidence before spending or trusting another service.",
                "Show CAP integration as the commerce rail after the source hashes, claim verdicts, and report hash are visible.",
                "Make the live-order gap explicit: the package reserves exact proof fields but does not claim a live CROO payment.",
            ],
            "shot_list": [
                {
                    "file_name": "01_public_repo_head.png",
                    "time": "0:00-0:25",
                    "screen": "Public GitHub repo and README",
                    "must_show": [
                        "repository URL",
                        "MIT license",
                        "latest public head {}".format(public_repo_state.get("head_commit", repo_state.get("commit", ""))),
                    ],
                    "spoken_claim": (
                        "This is the public source package; the bundle records whether it matches the judge-visible main branch."
                    ),
                },
                {
                    "file_name": "02_service_schema_listing.png",
                    "time": "0:25-0:55",
                    "screen": "service_schema.json",
                    "must_show": [
                        "TrustBrief CAP Verifier",
                        "Verified Research Brief",
                        "1 USDC price",
                        "20 minute SLA",
                        "schema requirements and deliverable",
                    ],
                    "spoken_claim": "TrustBrief is shaped as a paid Agent Store service with a concrete unit, price, SLA, and schema.",
                },
                {
                    "file_name": "03_judge_bundle_freshness.png",
                    "time": "0:55-1:35",
                    "screen": "outputs/judge_bundle.json",
                    "must_show": [
                        "artifact_freshness.status",
                        "fresh_for_public_demo",
                        "validation.tests.passed",
                        "proof.bundle_hash",
                    ],
                    "spoken_claim": "The judge bundle ties the demo artifacts to tests, hashes, and public-head freshness.",
                },
                {
                    "file_name": "04_report_provenance.png",
                    "time": "1:35-2:25",
                    "screen": "outputs/demo_report.json",
                    "must_show": [
                        "claim_assessments",
                        "source_ledger sha256 values",
                        "risk_flags",
                        "proof.report_hash",
                    ],
                    "spoken_claim": "The deliverable is machine-readable due diligence, with claim-level evidence and provenance hashes.",
                },
                {
                    "file_name": "05_cap_provider_lifecycle.png",
                    "time": "2:25-3:20",
                    "screen": "trustbrief_agent/cap_provider.py and outputs/mock_cap_demo.json",
                    "must_show": [
                        "NEGOTIATION_CREATED handler",
                        "ORDER_PAID handler",
                        "mock negotiation_id",
                        "mock order_id",
                        "mock tx_hash",
                    ],
                    "spoken_claim": "The offline CAP transcript exercises the same accept-and-deliver handlers used by live provider mode.",
                },
                {
                    "file_name": "06_buyer_manifest_gate.png",
                    "time": "3:20-4:20",
                    "screen": "outputs/buyer_composability_demo.json and outputs/live_commerce_evidence.json",
                    "must_show": [
                        "buyer correlation ID",
                        "downstream decision",
                        "payment_authorization.status",
                        "cap_lifecycle slots",
                        "hash_comparison.match_status",
                    ],
                    "spoken_claim": (
                        "A buyer agent can use this report hash and risk decision as a pre-spend gate before another purchase."
                    ),
                },
                {
                    "file_name": "07_live_proof_slot.png",
                    "time": "4:20-5:00",
                    "screen": "outputs/dorahacks_demo_package.md",
                    "must_show": [
                        "blocked credential reasons",
                        "proof targets",
                        "manual live steps",
                    ],
                    "spoken_claim": (
                        "The live proof slot names exactly what must be captured after dashboard credentials and payment authorization exist."
                    ),
                },
            ],
            "safe_spoken_claims": [
                "TrustBrief produces deterministic offline evidence today.",
                "The live provider code is wired for CROO negotiation and paid-order delivery.",
                "The package is ready for a credentialed Agent Store listing and first paid-order capture.",
                "No wallet action, DoraHacks submission, or live CROO order was performed by this offline generator.",
            ],
            "do_not_claim": [
                "The Agent Store listing is already live.",
                "A real CROO payment or escrow transaction has completed.",
                "The DoraHacks BUIDL has been submitted from this environment.",
                "TrustBrief has rank 1 or any judged placement before official results exist.",
            ],
            "publish_gate": {
                "ready_for_offline_demo": bool(
                    freshness.get("fresh_for_public_demo")
                    and test_result.get("passed")
                    and proof.get("report_hash")
                    and live_manifest_proof.get("manifest_hash")
                ),
                "requires_before_final_live_demo": [
                    "Agent Store listing URL",
                    "provider online evidence",
                    "real negotiation_id and order_id",
                    "payment or escrow transaction hash",
                    "delivery transaction hash",
                    "live delivered report hash",
                    "DoraHacks BUIDL URL or submission confirmation",
                ],
            },
        },
        "source_hash_block": {
            "repository_url": repo_url,
            "local_commit": repo_state.get("commit", ""),
            "public_head_commit": public_repo_state.get("head_commit", ""),
            "public_head_url": public_repo_state.get("head_commit_url", ""),
            "public_verified_at": public_repo_state.get("verified_at", ""),
            "bundle_hash": proof.get("bundle_hash", ""),
            "report_hash": proof.get("report_hash") or report_summary.get("report_hash", ""),
            "mock_tx_hash": proof.get("mock_tx_hash") or mock_cap_summary.get("tx_hash", ""),
            "request_input_hash": request_fingerprint.get("input_hash", ""),
            "buyer_correlation_id": buyer_correlation.get("correlation_id", ""),
            "buyer_downstream_decision": buyer_decision.get("decision", ""),
            "live_commerce_manifest_hash": live_manifest_proof.get("manifest_hash", ""),
            "live_payment_authorization_status": payment_authorization.get("status", ""),
            "live_hash_match_status": hash_comparison.get("match_status", ""),
            "key_asset_hashes": _key_asset_lines(judge_assets.get("key_asset_hashes", []) or []),
            "tests_passed": test_result.get("passed"),
        },
        "a2a_buyer_composability": {
            "correlation_id": buyer_correlation.get("correlation_id", ""),
            "buyer_agent": buyer_actors.get("buyer_agent", ""),
            "downstream_service": buyer_actors.get("downstream_service", ""),
            "trustbrief_report_hash": buyer_correlation.get("trustbrief_report_hash", ""),
            "mock_order_id": buyer_correlation.get("mock_order_id", ""),
            "downstream_decision": buyer_decision.get("decision", ""),
            "reason": buyer_decision.get("reason", ""),
            "live_payment_state": _require_dict(buyer_composability, "live_cap_placeholders").get("payment_state", ""),
        },
        "live_commerce_evidence": {
            "status": live_commerce_evidence.get("status", ""),
            "manifest_hash": live_manifest_proof.get("manifest_hash", ""),
            "payment_authorization_status": payment_authorization.get("status", ""),
            "explicit_human_authorization_present": payment_authorization.get("explicit_human_authorization_present", False),
            "cap_lifecycle_phases": [
                item.get("phase", "") for item in live_commerce_evidence.get("cap_lifecycle", []) if isinstance(item, dict)
            ],
            "x402_payment_states": [
                item.get("state", "") for item in live_commerce_evidence.get("x402_payment_states", []) if isinstance(item, dict)
            ],
            "tap_identity_status": tap_identity.get("trusted_agent_identity_status", ""),
            "hash_match_status": hash_comparison.get("match_status", ""),
            "capture_checklist": live_commerce_evidence.get("capture_checklist", []),
        },
        "credentialed_live_proof_slot": {
            "ready_to_attempt": readiness.get("ready_to_attempt", False),
            "gate_checks": gate_checks,
            "required_env_present": required_env,
            "blocked_reasons": blocked_reasons,
            "proof_targets": _proof_target_names(readiness),
            "manual_steps": readiness.get("manual_steps", []),
        },
    }
    return package


def render_submission_markdown(package: Dict[str, Any]) -> str:
    copy = _require_dict(package, "dorahacks_buidl_copy")
    capture_plan = _require_dict(package, "judge_demo_capture_plan")
    source = _require_dict(package, "source_hash_block")
    buyer = _require_dict(package, "a2a_buyer_composability")
    live_manifest = _require_dict(package, "live_commerce_evidence")
    live_slot = _require_dict(package, "credentialed_live_proof_slot")
    bundle = _require_dict(package, "source_bundle")

    lines = [
        "# DoraHacks Demo Package",
        "",
        "## BUIDL Copy",
        "",
        "- Project: {}".format(copy.get("project_name", "")),
        "- One-liner: {}".format(copy.get("one_liner", "")),
        "- Tracks: {}".format(", ".join(copy.get("tracks", []) or [])),
        "- Repository: {}".format(copy.get("repository_url", "")),
        "- Live proof status: {}".format(copy.get("live_proof_status", "")),
        "",
        "### Problem",
        "",
        str(copy.get("problem", "")),
        "",
        "### Solution",
        "",
        str(copy.get("solution", "")),
        "",
        "### CROO Integration",
        "",
        str(copy.get("croo_integration", "")),
        "",
        "### Demo Command",
        "",
        "```bash",
        str(copy.get("demo_command", "")),
        "```",
        "",
        "## Five-Minute Runbook",
        "",
    ]

    for item in package.get("five_minute_runbook", []):
        if not isinstance(item, dict):
            continue
        lines.append("- {} - {}: {}".format(item.get("time", ""), item.get("screen", ""), item.get("show", "")))

    lines.extend(["", "## Screenshot Checklist", ""])
    for item in package.get("screenshot_checklist", []):
        if not isinstance(item, dict):
            continue
        lines.append("- [{}] {}: {}".format(item.get("status", ""), item.get("artifact", ""), item.get("capture", "")))

    lines.extend(["", "## Judge Demo Capture Plan", ""])
    lines.append(str(capture_plan.get("recording_goal", "")))

    lines.extend(["", "### Positioning", ""])
    for item in capture_plan.get("positioning", []) or []:
        lines.append("- {}".format(item))

    lines.extend(["", "### Shot List", ""])
    for shot in capture_plan.get("shot_list", []) or []:
        if not isinstance(shot, dict):
            continue
        must_show = "; ".join(shot.get("must_show", []) or [])
        lines.append(
            "- {} - {} ({}): {}".format(
                shot.get("file_name", ""),
                shot.get("screen", ""),
                shot.get("time", ""),
                must_show,
            )
        )
        if shot.get("spoken_claim"):
            lines.append("  - Spoken claim: {}".format(shot.get("spoken_claim", "")))

    lines.extend(["", "### Safe Spoken Claims", ""])
    for item in capture_plan.get("safe_spoken_claims", []) or []:
        lines.append("- {}".format(item))

    lines.extend(["", "### Do Not Claim", ""])
    for item in capture_plan.get("do_not_claim", []) or []:
        lines.append("- {}".format(item))

    publish_gate = _require_dict(capture_plan, "publish_gate")
    lines.extend(["", "### Publish Gate", ""])
    lines.append("- Ready for offline demo: {}".format(publish_gate.get("ready_for_offline_demo", False)))
    for item in publish_gate.get("requires_before_final_live_demo", []) or []:
        lines.append("- Required before final live demo: {}".format(item))

    lines.extend(
        [
            "",
            "## Source And Hash Block",
            "",
            "- Bundle generated at: {}".format(bundle.get("generated_at", "")),
            "- Bundle freshness: {} (fresh_for_public_demo={})".format(
                bundle.get("freshness_status", ""),
                bundle.get("fresh_for_public_demo", False),
            ),
            "- Local commit: {}".format(source.get("local_commit", "")),
            "- Public head: {}".format(source.get("public_head_commit", "")),
            "- Public head URL: {}".format(source.get("public_head_url", "")),
            "- Bundle hash: {}".format(source.get("bundle_hash", "")),
            "- Report hash: {}".format(source.get("report_hash", "")),
            "- Mock CAP tx hash: {}".format(source.get("mock_tx_hash", "")),
            "- Request input hash: {}".format(source.get("request_input_hash", "")),
            "- Buyer correlation ID: {}".format(source.get("buyer_correlation_id", "")),
            "- Buyer downstream decision: {}".format(source.get("buyer_downstream_decision", "")),
            "- Live commerce manifest hash: {}".format(source.get("live_commerce_manifest_hash", "")),
            "- Live payment authorization status: {}".format(source.get("live_payment_authorization_status", "")),
            "- Live hash match status: {}".format(source.get("live_hash_match_status", "")),
            "- Tests passed: {}".format(source.get("tests_passed", "")),
            "",
            "### Key Asset Hashes",
            "",
        ]
    )
    for line in source.get("key_asset_hashes", []) or []:
        lines.append("- {}".format(line))

    lines.extend(
        [
            "",
            "## A2A Buyer Composability",
            "",
            "- Buyer agent: {}".format(buyer.get("buyer_agent", "")),
            "- Downstream service: {}".format(buyer.get("downstream_service", "")),
            "- Correlation ID: {}".format(buyer.get("correlation_id", "")),
            "- TrustBrief report hash: {}".format(buyer.get("trustbrief_report_hash", "")),
            "- Mock order ID: {}".format(buyer.get("mock_order_id", "")),
            "- Downstream decision: {}".format(buyer.get("downstream_decision", "")),
            "- Decision reason: {}".format(buyer.get("reason", "")),
            "- Live payment state: {}".format(buyer.get("live_payment_state", "")),
        ]
    )

    lines.extend(
        [
            "",
            "## Live Commerce Evidence Manifest",
            "",
            "- Status: {}".format(live_manifest.get("status", "")),
            "- Manifest hash: {}".format(live_manifest.get("manifest_hash", "")),
            "- Payment authorization: {}".format(live_manifest.get("payment_authorization_status", "")),
            "- Explicit human authorization present: {}".format(
                live_manifest.get("explicit_human_authorization_present", False)
            ),
            "- CAP lifecycle phases: {}".format(", ".join(live_manifest.get("cap_lifecycle_phases", []) or [])),
            "- x402 payment states: {}".format(", ".join(live_manifest.get("x402_payment_states", []) or [])),
            "- TAP identity status: {}".format(live_manifest.get("tap_identity_status", "")),
            "- Hash comparison: {}".format(live_manifest.get("hash_match_status", "")),
            "",
            "### Live Capture Checklist",
            "",
        ]
    )
    for item in live_manifest.get("capture_checklist", []) or []:
        if not isinstance(item, dict):
            continue
        lines.append("- [{}] {}: {}".format(item.get("status", ""), item.get("artifact", ""), item.get("capture", "")))

    lines.extend(["", "## Credentialed Live Proof Slot", ""])
    lines.append("- Ready to attempt: {}".format(live_slot.get("ready_to_attempt", False)))
    lines.append("- Gate checks: {}".format(json.dumps(live_slot.get("gate_checks", {}), sort_keys=True)))
    blocked_reasons = live_slot.get("blocked_reasons", []) or []
    if blocked_reasons:
        lines.append("- Blocked reasons:")
        for reason in blocked_reasons:
            lines.append("  - {}".format(reason))
    lines.append("- Proof targets: {}".format(", ".join(live_slot.get("proof_targets", []) or [])))
    manual_steps = live_slot.get("manual_steps", []) or []
    if manual_steps:
        lines.append("- Manual steps:")
        for step in manual_steps:
            lines.append("  - {}".format(step))

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a DoraHacks-ready demo package from a TrustBrief judge bundle.")
    parser.add_argument(
        "--bundle",
        default="outputs/judge_bundle.json",
        help="Path to outputs/judge_bundle.json or an equivalent evidence bundle.",
    )
    parser.add_argument("--output", "-o", help="Optional Markdown output path.")
    parser.add_argument("--json-output", help="Optional JSON output path.")
    args = parser.parse_args()

    bundle_path = Path(args.bundle)
    bundle = _load_json(bundle_path)
    package = build_submission_package(bundle, bundle_path=bundle_path)
    rendered = render_submission_markdown(package)
    if args.output:
        _write_text(Path(args.output), rendered)
    if args.json_output:
        _write_json(Path(args.json_output), package)
    if not args.output and not args.json_output:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
