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
    buyer_correlation = _require_dict(buyer_composability, "correlation")
    buyer_decision = _require_dict(buyer_composability, "downstream_decision")
    buyer_actors = _require_dict(buyer_composability, "actors")
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
                "--output outputs/judge_bundle.json"
            ),
            "live_proof_status": "blocked_by_credentials" if blocked_reasons else "ready_to_attempt",
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
                "screen": "outputs/requester_demo.json and outputs/buyer_composability_demo.json",
                "show": "Live-order gate checks, buyer-agent correlation ID, downstream purchase gate, and exact live proof fields.",
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
        ],
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
    source = _require_dict(package, "source_hash_block")
    buyer = _require_dict(package, "a2a_buyer_composability")
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
