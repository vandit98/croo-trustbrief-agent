from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Optional

from .core import canonical_json, sha256_text
from .requester_harness import build_requester_demo


def _require_dict(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def _default_purchase_context(request_payload: Dict[str, Any]) -> Dict[str, Any]:
    subject = str(request_payload.get("subject") or request_payload.get("task") or "the target service")
    return {
        "buyer_agent": "ProcurementRiskBuyer",
        "purchase_intent": "Decide whether to continue with a downstream agent or vendor purchase.",
        "downstream_service": "{} procurement or onboarding step".format(subject[:120]),
        "payment_authorization": "not_authorized_in_offline_demo",
        "max_authorized_spend_usdc": None,
    }


def _risk_codes(report_summary: Dict[str, Any]) -> Dict[str, Any]:
    flags = report_summary.get("risk_flags", [])
    if not isinstance(flags, list):
        flags = []
    codes = []
    severities = {"high": 0, "medium": 0, "low": 0}
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        code = str(flag.get("code") or "")
        severity = str(flag.get("severity") or "").lower()
        if code:
            codes.append(code)
        if severity in severities:
            severities[severity] += 1
    return {"codes": codes, "severity_counts": severities}


def _downstream_decision(report_summary: Dict[str, Any]) -> Dict[str, Any]:
    recommendation = str(report_summary.get("recommendation") or "")
    risk = _risk_codes(report_summary)
    if recommendation == "ready":
        decision = "approve_next_step"
        reason = "TrustBrief returned a ready recommendation with no blocking evidence flags."
    elif recommendation == "usable_with_caveats":
        decision = "manual_review_before_payment"
        reason = "TrustBrief found caveats, so a buyer agent should route the purchase for review before paying."
    else:
        decision = "hold_downstream_purchase"
        reason = "TrustBrief did not clear the target for autonomous spend."
    return {
        "decision": decision,
        "trustbrief_recommendation": recommendation,
        "risk_codes": risk["codes"],
        "severity_counts": risk["severity_counts"],
        "reason": reason,
    }


def _report_input_hash(request_payload: Dict[str, Any]) -> str:
    public_request = copy.deepcopy(request_payload)
    sources = public_request.get("sources", [])
    if isinstance(sources, list):
        public_request["sources"] = [
            {key: value for key, value in source.items() if key != "text"} if isinstance(source, dict) else source
            for source in sources
        ]
    return sha256_text(canonical_json(public_request))


def build_buyer_composability_packet(
    request_payload: Dict[str, Any],
    *,
    request_path: Optional[Path] = None,
    requester_demo: Optional[Dict[str, Any]] = None,
    purchase_context: Optional[Dict[str, Any]] = None,
    service_schema_path: Optional[Path] = None,
    analysis_now: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    requester_demo = requester_demo or build_requester_demo(
        request_payload,
        request_path=request_path,
        service_schema_path=service_schema_path,
        analysis_now=analysis_now,
    )
    request_fingerprint = _require_dict(requester_demo, "request_fingerprint")
    offline_preview = _require_dict(requester_demo, "offline_preview")
    report_summary = _require_dict(offline_preview, "report_summary")
    mock_cap_summary = _require_dict(offline_preview, "mock_cap_summary")
    readiness = _require_dict(requester_demo, "live_order_readiness")
    service = _require_dict(requester_demo, "service")
    context = dict(_default_purchase_context(request_payload))
    context.update(purchase_context or {})

    correlation_material = {
        "request_hash": request_fingerprint.get("input_hash", ""),
        "report_hash": report_summary.get("report_hash", ""),
        "service_name": service.get("service_name", ""),
        "downstream_service": context.get("downstream_service", ""),
    }
    correlation_id = "tb-a2a-{}".format(sha256_text(canonical_json(correlation_material))[:16])
    decision = _downstream_decision(report_summary)
    live_blockers = readiness.get("blocked_reasons", [])
    if not isinstance(live_blockers, list):
        live_blockers = []

    return {
        "buyer_composability_schema_version": "1.0.0",
        "purpose": "Show how a buyer agent uses TrustBrief as a pre-spend verification dependency.",
        "correlation": {
            "correlation_id": correlation_id,
            "request_input_hash": request_fingerprint.get("input_hash", ""),
            "report_input_hash": _report_input_hash(request_payload),
            "trustbrief_report_hash": report_summary.get("report_hash", ""),
            "mock_negotiation_id": mock_cap_summary.get("negotiation_id", ""),
            "mock_order_id": mock_cap_summary.get("order_id", ""),
            "mock_delivery_tx_hash": mock_cap_summary.get("tx_hash", ""),
        },
        "actors": {
            "buyer_agent": context.get("buyer_agent", ""),
            "verification_provider": "TrustBrief CAP Verifier",
            "downstream_service": context.get("downstream_service", ""),
        },
        "purchase_context": context,
        "a2a_sequence": [
            {
                "step": 1,
                "actor": "buyer_agent",
                "action": "prepare_downstream_purchase_intent",
                "status": "offline_simulated",
            },
            {
                "step": 2,
                "actor": "buyer_agent",
                "action": "call_trustbrief_before_spend",
                "status": "mock_cap_order",
                "mock_order_id": mock_cap_summary.get("order_id", ""),
            },
            {
                "step": 3,
                "actor": "trustbrief_provider",
                "action": "return_schema_report_with_hash",
                "status": "offline_verified",
                "trustbrief_report_hash": report_summary.get("report_hash", ""),
            },
            {
                "step": 4,
                "actor": "buyer_agent",
                "action": "gate_downstream_purchase",
                "status": decision["decision"],
            },
        ],
        "downstream_decision": decision,
        "machine_contract": {
            "required_before_downstream_payment": [
                "request_input_hash",
                "report_input_hash",
                "trustbrief_report_hash",
                "trustbrief_recommendation",
                "risk_codes",
            ],
            "pass_condition": "downstream_decision.decision == approve_next_step",
            "audit_join_key": correlation_id,
        },
        "live_cap_placeholders": {
            "payment_state": "not_attempted",
            "live_negotiation_id": "",
            "live_order_id": "",
            "live_payment_tx_hash": "",
            "live_delivery_tx_hash": "",
            "live_delivered_report_hash": "",
            "downstream_payment_tx_hash": "",
            "blocked_reasons": live_blockers,
            "no_wallet_action_performed": True,
        },
        "judge_talking_points": [
            "TrustBrief can be a dependency inside a larger buyer-agent workflow, not only a standalone report.",
            "The buyer packet carries one correlation ID across request, mock CAP order, report hash, and purchase gate.",
            "The offline packet reserves the exact fields that will hold live CAP and payment proofs after credentials exist.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an A2A buyer-composability proof packet for TrustBrief.")
    parser.add_argument("request", help="Path to request JSON.")
    parser.add_argument("--output", "-o", help="Write buyer-composability JSON to this path.")
    parser.add_argument("--service-schema", help="Optional path to service_schema.json.", default="")
    args = parser.parse_args()

    request_path = Path(args.request)
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("{} must decode to a JSON object".format(request_path))
    service_schema_path = Path(args.service_schema) if args.service_schema else None
    packet = build_buyer_composability_packet(
        payload,
        request_path=request_path,
        service_schema_path=service_schema_path,
    )
    rendered = json.dumps(packet, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
