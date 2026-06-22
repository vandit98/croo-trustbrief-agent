from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .core import analyze_request, canonical_json, sha256_text
from .mock_cap_harness import run_mock_cap_flow


def _read_json(path: Path) -> Dict[str, Any]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("{} must decode to a JSON object".format(path))
    return decoded


def _json_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return type(value).__name__


def _validate_array_items(values: Sequence[Any], item_schema: Dict[str, Any], field_name: str) -> List[str]:
    errors: List[str] = []
    expected_type = item_schema.get("type")
    properties = item_schema.get("properties", {})
    for index, value in enumerate(values):
        if expected_type == "string" and not isinstance(value, str):
            errors.append("{}[{}] must be string, got {}".format(field_name, index, _json_type_name(value)))
            continue
        if expected_type == "object":
            if not isinstance(value, dict):
                errors.append("{}[{}] must be object, got {}".format(field_name, index, _json_type_name(value)))
                continue
            if not any(key in value for key in ("url", "text", "path")):
                errors.append("{}[{}] must include at least one of url, text, or path".format(field_name, index))
            for key, property_schema in properties.items():
                if key in value and "type" in property_schema:
                    actual = _json_type_name(value[key])
                    if actual != property_schema["type"]:
                        errors.append(
                            "{}[{}].{} must be {}, got {}".format(
                                field_name, index, key, property_schema["type"], actual
                            )
                        )
    return errors


def validate_request_against_service_schema(
    request_payload: Dict[str, Any],
    service_schema: Dict[str, Any],
) -> Dict[str, Any]:
    schema = service_schema.get("requirements_schema", {})
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    errors: List[str] = []
    warnings: List[str] = []

    for field in required:
        value = request_payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, list) and not value):
            errors.append("missing required field: {}".format(field))

    for field_name, property_schema in properties.items():
        if field_name not in request_payload:
            continue
        value = request_payload[field_name]
        expected_type = property_schema.get("type")
        if expected_type:
            actual_type = _json_type_name(value)
            if actual_type != expected_type:
                errors.append("{} must be {}, got {}".format(field_name, expected_type, actual_type))
                continue
        if expected_type == "array":
            errors.extend(_validate_array_items(value, property_schema.get("items", {}), field_name))

    max_sources = request_payload.get("max_sources")
    if isinstance(max_sources, (int, float)) and max_sources <= 0:
        errors.append("max_sources must be positive when provided")
    sources = request_payload.get("sources")
    if isinstance(sources, list) and len(sources) > 6:
        warnings.append("request includes {} sources; TrustBrief currently uses the first 6".format(len(sources)))

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "required_fields": required,
    }


def _env_status(names: Sequence[str]) -> Dict[str, bool]:
    return {name: bool(os.environ.get(name)) for name in names}


def _service_readiness(service_schema: Dict[str, Any]) -> Dict[str, Any]:
    listing = service_schema.get("agent_store_listing", {})
    service = service_schema.get("service", {})
    required_listing = ("agent_name", "short_description", "tracks")
    required_service = ("service_name", "price_usdc", "deliverable_type", "requirements_type")

    missing_listing = [field for field in required_listing if not listing.get(field)]
    missing_service = [field for field in required_service if service.get(field) in ("", None, [])]

    return {
        "ready": not missing_listing and not missing_service,
        "missing_listing_fields": missing_listing,
        "missing_service_fields": missing_service,
        "listing_summary": {
            "agent_name": listing.get("agent_name", ""),
            "service_name": service.get("service_name", ""),
            "price_usdc": service.get("price_usdc"),
            "sla_minutes": service.get("sla_minutes"),
            "deliverable_type": service.get("deliverable_type", ""),
            "requirements_type": service.get("requirements_type", ""),
        },
    }


def _provider_start_command() -> str:
    return "python3.10 -m trustbrief_agent.cap_provider"


def _live_proof_targets(request_payload: Dict[str, Any], report_hash: str) -> List[Dict[str, str]]:
    return [
        {
            "artifact": "agent_store_listing",
            "why": "Proves the provider is actually listed in CROO Agent Store.",
            "capture": "Record the public listing URL plus one screenshot showing agent name, service name, price, and SLA.",
        },
        {
            "artifact": "provider_online_state",
            "why": "Shows the provider connected with valid CROO credentials.",
            "capture": "Capture provider startup logs after setting CROO_API_URL, CROO_WS_URL, and CROO_SDK_KEY.",
        },
        {
            "artifact": "paid_order_chain",
            "why": "This is the strongest judge-visible proof that CAP negotiation, payment, and delivery worked end to end.",
            "capture": "Capture the real negotiation_id, order_id, and tx_hash for this exact request payload.",
        },
        {
            "artifact": "delivered_report_hash",
            "why": "Lets judges compare the live-delivered object to the offline deterministic preview.",
            "capture": "Record the delivered report hash and compare it to offline preview report_hash={}.".format(report_hash),
        },
        {
            "artifact": "request_payload_fingerprint",
            "why": "Prevents ambiguity about which buyer request produced the live proof.",
            "capture": "Keep the exact JSON payload and its hash with the live proof package.",
        },
    ]


def build_requester_demo(
    request_payload: Dict[str, Any],
    *,
    request_path: Optional[Path] = None,
    service_schema_path: Optional[Path] = None,
    analysis_now: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    service_schema_path = service_schema_path or (repo_root / "service_schema.json")
    service_schema = _read_json(service_schema_path)
    validation = validate_request_against_service_schema(request_payload, service_schema)
    service_readiness = _service_readiness(service_schema)
    report = analyze_request(request_payload, now=analysis_now, use_openai=False)
    mock_transcript = asyncio.run(run_mock_cap_flow(request_payload, deliver_mode="schema", analysis_now=analysis_now))

    live_env = _env_status(["CROO_API_URL", "CROO_WS_URL", "CROO_SDK_KEY"])
    openai_env = _env_status(["OPENAI_API_KEY"])
    blocked_reasons: List[str] = []
    if not validation["valid"]:
        blocked_reasons.append("Request payload does not yet satisfy the Agent Store requirements schema.")
    if not service_readiness["ready"]:
        blocked_reasons.append("Service listing metadata is incomplete for a live Agent Store run.")
    missing_env = [name for name, present in live_env.items() if not present]
    if missing_env:
        blocked_reasons.append("Missing CROO runtime env vars: {}.".format(", ".join(missing_env)))
    live_ready = not blocked_reasons

    return {
        "requester_demo_schema_version": "1.0.0",
        "agent_store_target": service_schema.get("agent_store_listing", {}),
        "service": service_schema.get("service", {}),
        "request": request_payload,
        "request_fingerprint": {
            "request_path": str(request_path) if request_path else "",
            "input_hash": sha256_text(canonical_json(request_payload)),
            "claim_count": len(request_payload.get("claims", []) or []),
            "source_count": len(request_payload.get("sources", []) or []),
        },
        "schema_validation": validation,
        "offline_preview": {
            "report_summary": {
                "recommendation": report["recommendation"],
                "overall_evidence_score": report["overall_evidence_score"],
                "report_hash": report["proof"]["report_hash"],
                "risk_flags": report["risk_flags"],
            },
            "mock_cap_summary": {
                "negotiation_id": mock_transcript["negotiation_id"],
                "order_id": mock_transcript["order_id"],
                "tx_hash": mock_transcript["tx_hash"],
                "delivery_mode": mock_transcript["delivery_mode"],
            },
        },
        "judge_talking_points": [
            "The request is checked against the Agent Store requirements schema before delivery.",
            "The same payload can be shown in offline mode today and reused for a live CAP order later.",
            "The preview includes the deterministic report hash plus a mock negotiation to order to delivery chain.",
        ],
        "live_order_readiness": {
            "ready_to_attempt": live_ready,
            "gate_checks": {
                "request_schema_valid": validation["valid"],
                "service_listing_ready": service_readiness["ready"],
                "required_env_present": all(live_env.values()),
            },
            "required_env": live_env,
            "optional_env": openai_env,
            "service_readiness": service_readiness,
            "provider_start": {
                "command": _provider_start_command(),
                "working_directory": str(repo_root),
            },
            "proof_targets": _live_proof_targets(request_payload, report["proof"]["report_hash"]),
            "blocked_reasons": blocked_reasons,
            "manual_steps": [
                "Register the provider in the CROO Agent Store dashboard and paste service_schema.json.",
                "Export CROO_API_URL, CROO_WS_URL, and CROO_SDK_KEY, then start the provider with {}.".format(
                    _provider_start_command()
                ),
                "Submit this exact request payload from the requester side and capture the real negotiation_id, order_id, and tx_hash.",
                "Compare the live-delivered report hash to the offline preview hash before claiming the live proof chain.",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a requester-side TrustBrief demo packet with schema validation and CAP readiness notes."
    )
    parser.add_argument("request", help="Path to request JSON.")
    parser.add_argument("--output", "-o", help="Write the requester demo JSON to this path.")
    parser.add_argument("--service-schema", help="Optional path to service_schema.json.", default="")
    args = parser.parse_args()

    request_path = Path(args.request)
    service_schema_path = Path(args.service_schema) if args.service_schema else None
    payload = _read_json(request_path)
    packet = build_requester_demo(payload, request_path=request_path, service_schema_path=service_schema_path)
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
