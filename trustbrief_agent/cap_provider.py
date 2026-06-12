from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from typing import Any, Dict

from .core import analyze_request


LOG = logging.getLogger("trustbrief.cap_provider")


def _parse_requirements(raw: str) -> Dict[str, Any]:
    if not raw:
        return {"task": "Run a TrustBrief verification report.", "claims": [], "sources": []}
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, dict):
            return decoded
        return {"task": "Verify requester payload.", "claims": [str(decoded)], "sources": []}
    except json.JSONDecodeError:
        return {"task": raw, "subject": raw[:160], "claims": [], "sources": []}


async def main() -> int:
    try:
        from croo import AgentClient, Config, DeliverOrderRequest, DeliverableType, EventType
    except ImportError as exc:
        raise SystemExit(
            "croo-sdk is required for live CAP mode. Install with Python 3.10+: "
            "python -m pip install croo-sdk"
        ) from exc

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(levelname)s %(message)s")
    client = AgentClient(
        Config(
            base_url=os.environ.get("CROO_API_URL", "https://api.croo.network"),
            ws_url=os.environ.get("CROO_WS_URL", "wss://api.croo.network/ws"),
            rpc_url=os.environ.get("BASE_RPC_URL", ""),
        ),
        os.environ["CROO_SDK_KEY"],
    )
    stream = await client.connect_websocket()
    deliver_mode = os.environ.get("TRUSTBRIEF_DELIVERABLE_MODE", "schema").lower()
    use_openai = os.environ.get("TRUSTBRIEF_USE_OPENAI", "").lower() in {"1", "true", "yes"}
    auto_accept = os.environ.get("TRUSTBRIEF_AUTO_ACCEPT", "1").lower() not in {"0", "false", "no"}

    def on_negotiation_created(event: Any) -> None:
        async def _handle() -> None:
            if not auto_accept:
                LOG.info("negotiation received but auto-accept disabled negotiation_id=%s", event.negotiation_id)
                return
            try:
                result = await client.accept_negotiation(event.negotiation_id)
                LOG.info("accepted negotiation_id=%s order_id=%s", event.negotiation_id, result.order.order_id)
            except Exception:
                LOG.exception("failed to accept negotiation_id=%s", event.negotiation_id)

        asyncio.create_task(_handle())

    def on_order_paid(event: Any) -> None:
        async def _handle() -> None:
            try:
                order = await client.get_order(event.order_id)
                negotiation = await client.get_negotiation(order.negotiation_id)
                report = analyze_request(_parse_requirements(negotiation.requirements), use_openai=use_openai)
                rendered = json.dumps(report, sort_keys=True)
                if deliver_mode == "text":
                    req = DeliverOrderRequest(
                        deliverable_type=DeliverableType.TEXT,
                        deliverable_text=json.dumps(report, indent=2, sort_keys=True),
                    )
                else:
                    req = DeliverOrderRequest(
                        deliverable_type=DeliverableType.SCHEMA,
                        deliverable_schema=rendered,
                    )
                result = await client.deliver_order(event.order_id, req)
                LOG.info("delivered order_id=%s tx_hash=%s report_hash=%s", event.order_id, result.tx_hash, report["proof"]["report_hash"])
            except Exception:
                LOG.exception("failed to deliver order_id=%s", event.order_id)

        asyncio.create_task(_handle())

    stream.on(EventType.NEGOTIATION_CREATED, on_negotiation_created)
    stream.on(EventType.ORDER_PAID, on_order_paid)
    stream.on_any(lambda event: LOG.info("croo_event type=%s order_id=%s negotiation_id=%s", event.type, event.order_id, event.negotiation_id))

    LOG.info("TrustBrief provider online. Waiting for CROO orders.")
    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for signame in ("SIGINT", "SIGTERM"):
        if hasattr(signal, signame):
            loop.add_signal_handler(getattr(signal, signame), stop.set)
    await stop.wait()
    await stream.close()
    await client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

