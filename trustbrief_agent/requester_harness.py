from __future__ import annotations

import argparse
import asyncio
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


def build_requester_demo(
    request_payload: Dict[str, Any],
    *,
    request_path: Optional[Path] = None,
    service_schema_path: Optional[Path] = None,
) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    service_schema_path = service_schema_path or (repo_root / "service_schema.json")
    service_schema = _read_json(service_schema_path)
    validation = validate_request_against_service_schema(request_payload, service_schema)
    report = analyze_request(request_payload, use_openai=False)
    mock_transcript = asyncio.run(run_mock_cap_flow(request_payload, deliver_mode="schema"))

    live_env = _env_status(["CROO_API_URL", "CROO_WS_URL", "CROO_SDK_KEY"])
    openai_env = _env_status(["OPENAI_API_KEY"])
    live_ready = all(live_env.values())

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
            "required_env": live_env,
            "optional_env": openai_env,
            "blocked_reasons": [] if live_ready else [
                "Set CROO_API_URL, CROO_WS_URL, and CROO_SDK_KEY before attempting a live provider session.",
            ],
            "manual_steps": [
                "Register the provider in the CROO Agent Store dashboard and paste service_schema.json.",
                "Start the provider with python3.10 -m trustbrief_agent.cap_provider after setting CROO env vars.",
                "Submit this exact request payload from the requester side and capture the real negotiation_id, order_id, and tx_hash.",
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
