# TrustBrief CAP Verifier

TrustBrief is a paid, callable research and verification agent for the CROO Agent Store. It accepts a topic, claims, and public sources, then returns a schema deliverable with:

- claim-level support status and evidence snippets
- source SHA-256 provenance ledger
- risk flags for weak, partial, or missing evidence
- stable report hash for downstream agent audit trails
- optional OpenAI summary enhancement

Target tracks: **Research & Intelligence Agents** and **Data & Verification Agents**.

## Why This Fits CROO

CROO's quick start says provider agents are registered in the dashboard, services are configured in Agent Store, and live providers connect with `CROO_API_URL`, `CROO_WS_URL`, and `CROO_SDK_KEY`. The SDK then handles negotiation, payment, delivery, and WebSocket events.

TrustBrief uses that flow as a paid verification service:

1. requester agent orders `Verified Research Brief`
2. provider accepts the negotiation
3. requester pays through CAP escrow
4. TrustBrief verifies claims against sources
5. provider delivers structured JSON with hashes and risk flags

## Offline Demo

The local demo uses only the Python standard library.

```bash
cd /Users/vandit/Downloads/exploring/kaggle/croo-trustbrief-agent
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m trustbrief_agent.cli examples/sample_request.json --output outputs/demo_report.json
python3 -m trustbrief_agent.mock_cap_harness examples/sample_request.json --output outputs/mock_cap_demo.json
```

Inspect `outputs/demo_report.json` for the report hash, source ledger, and claim assessments.
Inspect `outputs/mock_cap_demo.json` for a judge-visible mock negotiation, order acceptance, delivery transcript, and report hash.

## Live CROO Provider

Live CAP mode requires Python 3.10+ and the official CROO Python SDK.

```bash
python3.10 -m pip install croo-sdk

export CROO_API_URL="https://api.croo.network"
export CROO_WS_URL="wss://api.croo.network/ws"
export CROO_SDK_KEY="croo_sk_...provider_key..."

python3.10 -m trustbrief_agent.cap_provider
```

Optional OpenAI enhancement:

```bash
export TRUSTBRIEF_USE_OPENAI=1
export OPENAI_API_KEY="..."
export TRUSTBRIEF_OPENAI_MODEL="gpt-5.5"
```

If OpenAI is not configured, TrustBrief still produces the deterministic source-ledger report.

## Offline CAP Lifecycle Proof

`trustbrief_agent/mock_cap_harness.py` simulates the same two provider transitions that matter in live CAP mode:

1. `NEGOTIATION_CREATED` -> `accept_negotiation`
2. `ORDER_PAID` -> `deliver_order`

The harness reuses the real provider handlers from `trustbrief_agent/cap_provider.py`, so the offline transcript exercises the same request parsing, report generation, and deliverable rendering path that live CROO delivery uses.

## Agent Store Service Setup

Use [service_schema.json](service_schema.json) while configuring the dashboard:

- Agent name: `TrustBrief CAP Verifier`
- Service name: `Verified Research Brief`
- Price: `1.00 USDC`
- SLA: `0h 20m`
- Requirements: `Schema`
- Deliverable: `Schema`

The dashboard registration and API key issuance are intentionally not automated because CROO docs state those are Agent Store account setup steps, not SDK operations.

## Request Shape

```json
{
  "task": "Verify acquisition-readiness claims for a vendor.",
  "subject": "Example Vendor",
  "claims": [
    "The vendor publishes SOC 2 compliance material.",
    "The vendor supports API-based onboarding."
  ],
  "sources": [
    {"label": "security page", "url": "https://example.com/security"},
    {"label": "API docs", "url": "https://example.com/docs"}
  ]
}
```

Inline source text is supported for private pre-reads:

```json
{"label": "pasted memo", "text": "Service registration is created in the dashboard."}
```

## Deliverable Highlights

The report contains:

- `recommendation`: `ready`, `usable_with_caveats`, or `needs_review`
- `claim_assessments`: claim, status, confidence score, evidence snippets
- `source_ledger`: URL, title, character count, SHA-256, fetch errors
- `risk_flags`: severity-coded issues
- `proof`: input hash, source bundle hash, report hash, algorithm version

## Repository Status

This repository is MIT licensed and ready to publish as the hackathon GitHub repo after the CROO dashboard credentials and DoraHacks BUIDL are created.
