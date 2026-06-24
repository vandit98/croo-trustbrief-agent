from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .buyer_composability import build_buyer_composability_packet
from .core import canonical_json, sha256_text
from .requester_harness import build_requester_demo


REQUIRED_LIVE_ENV = [
    "CROO_API_URL",
    "CROO_WS_URL",
    "CROO_SDK_KEY",
    "CROO_AGENT_ID",
    "CROO_SERVICE_ID",
    "CROO_REQUESTER_SDK_KEY",
]


def _read_json(path: Path) -> Dict[str, Any]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("{} must decode to a JSON object".format(path))
    return decoded


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_dict(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def _env_status(names: Sequence[str]) -> Dict[str, bool]:
    return {name: bool(os.environ.get(name)) for name in names}


def _cap_lifecycle_slots(mock_cap_summary: Dict[str, Any], report_hash: str) -> List[Dict[str, Any]]:
    return [
        {
            "phase": "negotiate",
            "cap_state": "Negotiate",
            "offline_reference": {
                "mock_negotiation_id": mock_cap_summary.get("negotiation_id", ""),
            },
            "live_capture": {
                "negotiation_id": "",
                "created_at": "",
                "accepted_at": "",
                "agent_store_listing_url": "",
                "provider_online_screenshot": "",
            },
            "judge_proof": "CROO created the buyer/provider negotiation for this exact request payload.",
        },
        {
            "phase": "lock",
            "cap_state": "Lock",
            "offline_reference": {
                "mock_order_id": mock_cap_summary.get("order_id", ""),
            },
            "live_capture": {
                "order_id": "",
                "escrow_or_payment_tx_hash": "",
                "payment_submitted_at": "",
                "requester_agent_id": "",
                "requester_wallet_funding_screenshot": "",
            },
            "judge_proof": "Requester payment was authorized and locked before provider delivery.",
        },
        {
            "phase": "deliver",
            "cap_state": "Deliver",
            "offline_reference": {
                "mock_delivery_tx_hash": mock_cap_summary.get("tx_hash", ""),
                "offline_preview_report_hash": report_hash,
            },
            "live_capture": {
                "delivery_tx_hash": "",
                "delivered_report_hash": "",
                "delivered_at": "",
                "provider_delivery_log": "",
            },
            "judge_proof": "Provider delivered the TrustBrief schema report through CAP.",
        },
        {
            "phase": "clear",
            "cap_state": "Clear",
            "offline_reference": {},
            "live_capture": {
                "settlement_tx_hash": "",
                "settlement_status": "",
                "cleared_at": "",
                "dispute_status": "",
            },
            "judge_proof": "Payment settled or cleared without a dispute after delivery.",
        },
    ]


def _x402_payment_states() -> List[Dict[str, str]]:
    return [
        {
            "state": "payment_required",
            "status": "pending_live_order",
            "capture": "Requester sees service price, target service ID, and payment requirements before paying.",
            "live_value": "",
        },
        {
            "state": "payment_submitted",
            "status": "pending_live_order",
            "capture": "Requester submits payment or escrow lock for the CAP order.",
            "live_value": "",
        },
        {
            "state": "payment_completed",
            "status": "pending_live_order",
            "capture": "CAP reports completed delivery and settlement/clear state.",
            "live_value": "",
        },
        {
            "state": "payment_failed_or_timeout",
            "status": "reserved_for_negative_proof",
            "capture": "If the first live attempt fails, record the exact error, timeout, or failed payment state.",
            "live_value": "",
        },
    ]


def build_live_commerce_evidence_manifest(
    request_payload: Dict[str, Any],
    *,
    request_path: Optional[Path] = None,
    requester_demo: Optional[Dict[str, Any]] = None,
    buyer_composability: Optional[Dict[str, Any]] = None,
    service_schema_path: Optional[Path] = None,
    analysis_now: Optional[dt.datetime] = None,
    public_repo_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    analysis_now = analysis_now or dt.datetime.now(dt.timezone.utc)
    generated_at = analysis_now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    requester_demo = requester_demo or build_requester_demo(
        request_payload,
        request_path=request_path,
        service_schema_path=service_schema_path,
        analysis_now=analysis_now,
    )
    buyer_composability = buyer_composability or build_buyer_composability_packet(
        request_payload,
        request_path=request_path,
        requester_demo=requester_demo,
        service_schema_path=service_schema_path,
        analysis_now=analysis_now,
    )

    agent_store_target = _require_dict(requester_demo, "agent_store_target")
    service = _require_dict(requester_demo, "service")
    request_fingerprint = _require_dict(requester_demo, "request_fingerprint")
    offline_preview = _require_dict(requester_demo, "offline_preview")
    report_summary = _require_dict(offline_preview, "report_summary")
    mock_cap_summary = _require_dict(offline_preview, "mock_cap_summary")
    readiness = _require_dict(requester_demo, "live_order_readiness")
    buyer_correlation = _require_dict(buyer_composability, "correlation")
    buyer_decision = _require_dict(buyer_composability, "downstream_decision")
    live_env = _env_status(REQUIRED_LIVE_ENV)
    missing_env = [name for name, present in live_env.items() if not present]
    explicit_payment_authorization = os.environ.get("TRUSTBRIEF_LIVE_PAYMENT_AUTHORIZED", "").lower() in {
        "1",
        "true",
        "yes",
    }
    requester_wallet_funded = os.environ.get("CROO_REQUESTER_WALLET_FUNDED", "").lower() in {"1", "true", "yes"}
    blocked_reasons = list(readiness.get("blocked_reasons", []) or [])
    if missing_env:
        blocked_reasons.append("Missing live commerce env vars: {}.".format(", ".join(missing_env)))
    if not explicit_payment_authorization:
        blocked_reasons.append("No explicit human authorization for a live paid CROO order was present.")
    if not requester_wallet_funded:
        blocked_reasons.append("Requester funding confirmation was not present.")

    status = "ready_for_credentialed_capture" if not blocked_reasons else "blocked_by_credentials"
    report_hash = str(report_summary.get("report_hash", ""))
    request_input_hash = str(request_fingerprint.get("input_hash", ""))
    report_input_hash = str(buyer_correlation.get("report_input_hash", ""))

    manifest: Dict[str, Any] = {
        "live_commerce_evidence_schema_version": "1.0.0",
        "generated_at": generated_at,
        "status": status,
        "purpose": "Deterministic capture contract for the first credentialed TrustBrief CROO paid-order proof.",
        "service_target": {
            "agent_name": agent_store_target.get("agent_name", ""),
            "service_name": service.get("service_name", ""),
            "price_usdc": service.get("price_usdc"),
            "sla_minutes": service.get("sla_minutes"),
            "deliverable_type": service.get("deliverable_type", ""),
            "requirements_type": service.get("requirements_type", ""),
            "agent_store_listing_url": "",
            "provider_service_id": "",
        },
        "request_identity": {
            "request_path": str(request_path) if request_path else "",
            "request_input_hash": request_input_hash,
            "report_input_hash": report_input_hash,
            "claim_count": request_fingerprint.get("claim_count", 0),
            "source_count": request_fingerprint.get("source_count", 0),
            "buyer_correlation_id": buyer_correlation.get("correlation_id", ""),
            "downstream_decision": buyer_decision.get("decision", ""),
        },
        "payment_authorization": {
            "status": "authorized" if explicit_payment_authorization else "not_authorized",
            "explicit_human_authorization_present": explicit_payment_authorization,
            "requester_wallet_funding_confirmed": requester_wallet_funded,
            "max_authorized_spend_usdc": service.get("price_usdc"),
            "required_before_live_run": [
                "Confirm CROO requester wallet has enough USDC for the service price.",
                "Record explicit human authorization for this exact request hash and max spend.",
                "Keep requester/provider credentials out of logs and screenshots.",
            ],
        },
        "ap2_style_intent": {
            "intent_status": "not_signed",
            "user_intent": {
                "action": "buy_verified_research_brief",
                "service_name": service.get("service_name", ""),
                "request_input_hash": request_input_hash,
                "expected_report_hash_before_live_run": report_hash,
                "max_spend_usdc": service.get("price_usdc"),
            },
            "authorization_artifacts": {
                "intent_id": "",
                "signed_mandate_hash": "",
                "authorization_note_or_ticket": "",
            },
        },
        "x402_payment_states": _x402_payment_states(),
        "tap_style_identity_intent": {
            "trusted_agent_identity_status": "pending_croo_listing",
            "provider_agent": {
                "name": agent_store_target.get("agent_name", ""),
                "agent_store_listing_url": "",
                "croo_agent_id": "",
            },
            "merchant_or_service_target": {
                "service_name": service.get("service_name", ""),
                "croo_service_id": "",
                "price_usdc": service.get("price_usdc"),
            },
            "transaction_intent_fields": {
                "request_input_hash": request_input_hash,
                "buyer_correlation_id": buyer_correlation.get("correlation_id", ""),
                "timestamp": "",
                "session_id": "",
            },
        },
        "cap_lifecycle": _cap_lifecycle_slots(mock_cap_summary, report_hash),
        "hash_comparison": {
            "offline_preview_report_hash": report_hash,
            "live_delivered_report_hash": "",
            "match_status": "pending_live_delivery",
            "comparison_rule": "After live delivery, compare proof.report_hash from the delivered schema to the offline preview hash for this exact request.",
        },
        "capture_checklist": [
            {
                "artifact": "agent_store_listing",
                "capture": "Listing URL plus screenshot with agent name, service name, price, SLA, and schema fields.",
                "status": "pending_credentials",
            },
            {
                "artifact": "provider_online_state",
                "capture": "Provider startup log after CROO_API_URL, CROO_WS_URL, and CROO_SDK_KEY are set.",
                "status": "pending_credentials",
            },
            {
                "artifact": "payment_authorization",
                "capture": "Human approval note, request hash, max spend, requester funding confirmation, and no secret values.",
                "status": "pending_authorization",
            },
            {
                "artifact": "cap_order_chain",
                "capture": "Real negotiation_id, order_id, payment/escrow tx hash, delivery tx hash, and clear/settlement state.",
                "status": "pending_live_order",
            },
            {
                "artifact": "live_vs_offline_hash",
                "capture": "Offline preview report hash and live delivered report hash comparison.",
                "status": "pending_live_delivery",
            },
            {
                "artifact": "demo_video_segment",
                "capture": "Short clip showing listing, provider online, requester order, CAP IDs, delivered hash, and package manifest.",
                "status": "pending_recording",
            },
        ],
        "credential_gate": {
            "ready_to_attempt": status == "ready_for_credentialed_capture",
            "required_env_present": live_env,
            "missing_env": missing_env,
            "blocked_reasons": blocked_reasons,
        },
        "public_repo_state": dict(public_repo_state or {}),
        "safety": {
            "no_wallet_action_performed": True,
            "no_dorahacks_submission_performed": True,
            "no_live_croo_order_claimed": True,
            "credentials_are_not_recorded": True,
        },
    }
    stable = dict(manifest)
    manifest["proof"] = {
        "manifest_hash": sha256_text(canonical_json(stable)),
        "request_input_hash": request_input_hash,
        "report_input_hash": report_input_hash,
        "offline_preview_report_hash": report_hash,
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a live-commerce evidence manifest for TrustBrief.")
    parser.add_argument("request", help="Path to request JSON.")
    parser.add_argument("--output", "-o", help="Write live-commerce evidence JSON to this path.")
    parser.add_argument("--service-schema", help="Optional path to service_schema.json.", default="")
    args = parser.parse_args()

    request_path = Path(args.request)
    payload = _read_json(request_path)
    service_schema_path = Path(args.service_schema) if args.service_schema else None
    manifest = build_live_commerce_evidence_manifest(
        payload,
        request_path=request_path,
        service_schema_path=service_schema_path,
    )
    if args.output:
        _write_json(Path(args.output), manifest)
    else:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
