from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .core import canonical_json, sha256_text


REQUIRED_PROVIDER_ENV = [
    "CROO_API_URL",
    "CROO_WS_URL",
    "CROO_SDK_KEY",
    "CROO_AGENT_ID",
    "CROO_SERVICE_ID",
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


def _schema_field_names(schema: Dict[str, Any]) -> List[str]:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return []
    return sorted(str(name) for name in properties)


def _missing_listing_fields(listing: Dict[str, Any], service: Dict[str, Any]) -> List[str]:
    checks = {
        "agent_store_listing.agent_name": listing.get("agent_name"),
        "agent_store_listing.short_description": listing.get("short_description"),
        "agent_store_listing.skill_tags": listing.get("skill_tags"),
        "agent_store_listing.tracks": listing.get("tracks"),
        "service.service_name": service.get("service_name"),
        "service.price_usdc": service.get("price_usdc"),
        "service.sla_minutes": service.get("sla_minutes"),
        "service.deliverable_type": service.get("deliverable_type"),
        "service.requirements_type": service.get("requirements_type"),
        "service.description": service.get("description"),
    }
    return [name for name, value in checks.items() if value in ("", None, [])]


def build_agent_store_listing_kit(
    *,
    service_schema_path: Optional[Path] = None,
    analysis_now: Optional[dt.datetime] = None,
    public_repo_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    service_schema_path = service_schema_path or (repo_root / "service_schema.json")
    service_schema = _read_json(service_schema_path)
    listing = _require_dict(service_schema, "agent_store_listing")
    service = _require_dict(service_schema, "service")
    requirements_schema = _require_dict(service_schema, "requirements_schema")
    deliverable_schema = _require_dict(service_schema, "deliverable_schema")
    generated_at = (analysis_now or dt.datetime.now(dt.timezone.utc)).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    public_repo_state = dict(public_repo_state or {})
    provider_env = _env_status(REQUIRED_PROVIDER_ENV)
    missing_env = [name for name, present in provider_env.items() if not present]
    missing_fields = _missing_listing_fields(listing, service)
    repo_url = public_repo_state.get("repository_url", "https://github.com/vandit98/croo-trustbrief-agent")

    kit: Dict[str, Any] = {
        "agent_store_listing_kit_schema_version": "1.0.0",
        "generated_at": generated_at,
        "purpose": "Manual CROO Agent Store listing kit and proof-capture contract for TrustBrief.",
        "source": {
            "service_schema_path": str(service_schema_path),
            "service_schema_sha256": sha256_text(service_schema_path.read_text(encoding="utf-8")),
            "public_repository_url": repo_url,
            "public_head_commit": public_repo_state.get("head_commit", ""),
            "public_head_url": public_repo_state.get("head_commit_url", ""),
        },
        "dashboard_copy": {
            "agent_name": listing.get("agent_name", ""),
            "short_description": listing.get("short_description", ""),
            "skill_tags": listing.get("skill_tags", []),
            "tracks": listing.get("tracks", []),
            "service_name": service.get("service_name", ""),
            "service_description": service.get("description", ""),
            "price_usdc": service.get("price_usdc"),
            "sla_minutes": service.get("sla_minutes"),
            "requirements_type": service.get("requirements_type", ""),
            "deliverable_type": service.get("deliverable_type", ""),
            "repository_url": repo_url,
            "long_description": (
                "TrustBrief is a paid CROO Agent Store service for buyer agents that need source-backed "
                "due diligence before spending, trusting a listing, or escalating a workflow. It returns "
                "claim assessments, evidence snippets, SHA-256 source provenance, risk flags, and a stable "
                "report hash suitable for downstream agent audit trails."
            ),
        },
        "schema_paste_targets": [
            {
                "dashboard_field": "requirements_schema",
                "source": "service_schema.json.requirements_schema",
                "required_fields": requirements_schema.get("required", []),
                "property_names": _schema_field_names(requirements_schema),
                "json": requirements_schema,
            },
            {
                "dashboard_field": "deliverable_schema",
                "source": "service_schema.json.deliverable_schema",
                "required_fields": deliverable_schema.get("required", []),
                "property_names": _schema_field_names(deliverable_schema),
                "json": deliverable_schema,
            },
        ],
        "readiness": {
            "listing_copy_ready": not missing_fields,
            "missing_listing_fields": missing_fields,
            "provider_env_ready": not missing_env,
            "required_provider_env_present": provider_env,
            "missing_provider_env": missing_env,
            "dashboard_status": "ready_to_create_listing" if not missing_fields else "incomplete_listing_copy",
            "live_provider_status": "ready_to_start_provider" if not missing_env else "blocked_by_credentials",
        },
        "dashboard_steps": [
            "Create or open the TrustBrief provider in the CROO Agent Store dashboard.",
            "Paste the dashboard_copy fields exactly; keep the price at 1.00 USDC and SLA at 20 minutes.",
            "Paste requirements_schema and deliverable_schema from schema_paste_targets without editing field names.",
            "Publish or save the listing, then record the public listing URL, CROO agent ID, and service ID.",
            "Export the provider env vars locally and start python3.10 -m trustbrief_agent.cap_provider.",
            "Use examples/sample_request.json for the first live paid order and compare the delivered report hash.",
        ],
        "capture_contract": {
            "proof_fields": {
                "agent_store_listing_url": "",
                "croo_agent_id": "",
                "croo_service_id": "",
                "provider_online_screenshot": "",
                "service_schema_screenshot": "",
                "first_negotiation_id": "",
                "first_order_id": "",
                "first_payment_or_escrow_tx_hash": "",
                "first_delivery_tx_hash": "",
                "first_delivered_report_hash": "",
            },
            "screenshot_files": [
                {
                    "file_name": "agent_store_01_listing_overview.png",
                    "must_show": "Agent name, short description, tags, track fit, repository URL, and published listing URL.",
                },
                {
                    "file_name": "agent_store_02_service_schema.png",
                    "must_show": "Service name, price, SLA, requirements schema, and deliverable schema.",
                },
                {
                    "file_name": "agent_store_03_provider_ids_redacted.png",
                    "must_show": "CROO agent ID and service ID; do not show SDK keys, wallet secrets, or tokens.",
                },
                {
                    "file_name": "agent_store_04_provider_online.png",
                    "must_show": "Provider startup log proving the WebSocket listener is online with secrets redacted.",
                },
                {
                    "file_name": "agent_store_05_first_paid_order.png",
                    "must_show": "Real negotiation ID, order ID, payment or escrow hash, delivery hash, and report hash.",
                },
            ],
        },
        "safe_claims": [
            "The repository contains the exact Agent Store listing copy and schemas to paste.",
            "The offline bundle proves deterministic report generation and CAP handler behavior.",
            "The listing kit names the fields needed to capture one live CROO paid order after credentials exist.",
        ],
        "do_not_claim": [
            "The Agent Store listing is live before a listing URL and screenshot are captured.",
            "A CROO payment, escrow, delivery, or settlement happened before real IDs and hashes are recorded.",
            "SDK keys, wallet secrets, or dashboard credentials are safe to show in the demo.",
            "DoraHacks submission is complete before the authenticated BUIDL page confirms it.",
        ],
        "safety": {
            "records_secret_values": False,
            "performs_wallet_action": False,
            "performs_dorahacks_submission": False,
            "claims_live_listing": False,
            "claims_live_order": False,
        },
    }
    stable = dict(kit)
    kit["proof"] = {
        "listing_kit_hash": sha256_text(canonical_json(stable)),
        "service_schema_sha256": kit["source"]["service_schema_sha256"],
    }
    return kit


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a CROO Agent Store listing kit for TrustBrief.")
    parser.add_argument("--service-schema", default="service_schema.json", help="Path to service_schema.json.")
    parser.add_argument("--public-repo-url", help="Optional verified public repository URL.")
    parser.add_argument("--public-head-commit", help="Optional verified public head commit SHA.")
    parser.add_argument("--public-head-url", help="Optional verified public commit URL.")
    parser.add_argument("--public-verified-at", help="Optional public verification timestamp.")
    parser.add_argument("--output", "-o", help="Write listing kit JSON to this path.")
    args = parser.parse_args()

    public_repo_state = {
        "repository_url": args.public_repo_url,
        "head_commit": args.public_head_commit,
        "head_commit_url": args.public_head_url,
        "verified_at": args.public_verified_at,
    }
    public_repo_state = {key: value for key, value in public_repo_state.items() if value}
    kit = build_agent_store_listing_kit(
        service_schema_path=Path(args.service_schema),
        public_repo_state=public_repo_state,
    )
    if args.output:
        _write_json(Path(args.output), kit)
    else:
        print(json.dumps(kit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
