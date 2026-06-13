from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cap_provider import handle_negotiation_created, handle_order_paid


@dataclass
class _Order:
    order_id: str
    negotiation_id: str


@dataclass
class _Negotiation:
    negotiation_id: str
    requirements: str


@dataclass
class _AcceptResult:
    order: _Order


@dataclass
class _DeliverResult:
    tx_hash: str


@dataclass
class _Event:
    type: str
    negotiation_id: str = ""
    order_id: str = ""


class _DeliverableType:
    SCHEMA = "schema"
    TEXT = "text"


class _DeliverOrderRequest:
    def __init__(
        self,
        *,
        deliverable_type: str,
        deliverable_schema: str = "",
        deliverable_text: str = "",
    ) -> None:
        self.deliverable_type = deliverable_type
        self.deliverable_schema = deliverable_schema
        self.deliverable_text = deliverable_text


class MockCapClient:
    def __init__(self, requirements: Dict[str, Any]) -> None:
        self.negotiation = _Negotiation(
            negotiation_id="neg_mock_001",
            requirements=json.dumps(requirements, sort_keys=True),
        )
        self.order: Optional[_Order] = None
        self.accepted_negotiations: List[str] = []
        self.delivery_requests: List[_DeliverOrderRequest] = []

    async def accept_negotiation(self, negotiation_id: str) -> _AcceptResult:
        self.accepted_negotiations.append(negotiation_id)
        self.order = _Order(order_id="ord_mock_001", negotiation_id=negotiation_id)
        return _AcceptResult(order=self.order)

    async def get_order(self, order_id: str) -> _Order:
        if not self.order or self.order.order_id != order_id:
            raise ValueError("unknown order_id: {}".format(order_id))
        return self.order

    async def get_negotiation(self, negotiation_id: str) -> _Negotiation:
        if self.negotiation.negotiation_id != negotiation_id:
            raise ValueError("unknown negotiation_id: {}".format(negotiation_id))
        return self.negotiation

    async def deliver_order(self, order_id: str, request: _DeliverOrderRequest) -> _DeliverResult:
        if not self.order or self.order.order_id != order_id:
            raise ValueError("cannot deliver unknown order_id: {}".format(order_id))
        self.delivery_requests.append(request)
        return _DeliverResult(tx_hash="0xmockdeliver{:02d}".format(len(self.delivery_requests)))


def _read_payload(path: str) -> Dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("request JSON must decode to an object")
    return decoded


async def run_mock_cap_flow(request_payload: Dict[str, Any], deliver_mode: str = "schema") -> Dict[str, Any]:
    client = MockCapClient(request_payload)

    negotiation_event = _Event(type="NEGOTIATION_CREATED", negotiation_id=client.negotiation.negotiation_id)
    accept_result = await handle_negotiation_created(client, negotiation_event, auto_accept=True)

    paid_event = _Event(type="ORDER_PAID", negotiation_id=client.negotiation.negotiation_id, order_id=accept_result.order.order_id)
    delivery = await handle_order_paid(
        client,
        paid_event,
        deliver_mode=deliver_mode,
        use_openai=False,
        deliver_order_request_cls=_DeliverOrderRequest,
        deliverable_type=_DeliverableType,
    )

    report = delivery["report"]
    request = delivery["request"]
    return {
        "mock_cap_demo_version": "1.0.0",
        "negotiation_id": client.negotiation.negotiation_id,
        "order_id": accept_result.order.order_id,
        "accepted_negotiations": client.accepted_negotiations,
        "delivery_mode": request.deliverable_type,
        "tx_hash": delivery["result"].tx_hash,
        "request_summary": {
            "task": request_payload.get("task", ""),
            "subject": request_payload.get("subject", ""),
            "claim_count": len(request_payload.get("claims", []) or []),
            "source_count": len(request_payload.get("sources", []) or []),
        },
        "report_summary": {
            "recommendation": report["recommendation"],
            "overall_evidence_score": report["overall_evidence_score"],
            "report_hash": report["proof"]["report_hash"],
            "source_bundle_hash": report["proof"]["source_bundle_hash"],
            "risk_flags": report["risk_flags"],
        },
        "delivered_preview": {
            "schema_bytes": len(request.deliverable_schema.encode("utf-8")) if request.deliverable_schema else 0,
            "text_bytes": len(request.deliverable_text.encode("utf-8")) if request.deliverable_text else 0,
        },
        "report": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an offline mock CROO CAP order lifecycle for TrustBrief.")
    parser.add_argument("request", help="Path to request JSON.")
    parser.add_argument("--output", "-o", help="Write mock lifecycle JSON to this path.")
    parser.add_argument(
        "--deliver-mode",
        choices=("schema", "text"),
        default="schema",
        help="Render the mock deliverable using the same provider mode as live CAP delivery.",
    )
    args = parser.parse_args()

    transcript = asyncio.run(run_mock_cap_flow(_read_payload(args.request), deliver_mode=args.deliver_mode))
    rendered = json.dumps(transcript, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
