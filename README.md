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
python3 -m trustbrief_agent.requester_harness examples/sample_request.json --output outputs/requester_demo.json
python3 -m trustbrief_agent.buyer_composability examples/sample_request.json --output outputs/buyer_composability_demo.json
python3 -m trustbrief_agent.live_commerce_evidence examples/sample_request.json --output outputs/live_commerce_evidence.json
python3 -m trustbrief_agent.evidence_bundle examples/sample_request.json --output outputs/judge_bundle.json
python3 -m trustbrief_agent.submission_package \
  --bundle outputs/judge_bundle.json \
  --output outputs/dorahacks_demo_package.md \
  --json-output outputs/dorahacks_demo_package.json
```

Or refresh the full judge pack in one command:

```bash
python3 -m trustbrief_agent.evidence_bundle \
  examples/sample_request.json \
  --report-output outputs/demo_report.json \
  --mock-output outputs/mock_cap_demo.json \
  --requester-output outputs/requester_demo.json \
  --buyer-output outputs/buyer_composability_demo.json \
  --live-commerce-output outputs/live_commerce_evidence.json \
  --public-repo-url https://github.com/vandit98/croo-trustbrief-agent \
  --public-default-branch main \
  --public-visibility public \
  --public-head-commit <verified-public-head-sha> \
  --public-head-url https://github.com/vandit98/croo-trustbrief-agent/commit/<verified-public-head-sha> \
  --public-verified-at <verified-at-iso8601> \
  --public-verification-source "GitHub connector" \
  --output outputs/judge_bundle.json
```

Inspect `outputs/demo_report.json` for the report hash, source ledger, and claim assessments.
Inspect `outputs/mock_cap_demo.json` for a judge-visible mock negotiation, order acceptance, delivery transcript, and report hash.
Inspect `outputs/requester_demo.json` for request-schema validation, buyer-facing talking points, live-order gate checks, provider launch command, and the exact proof targets to capture once CROO credentials exist.
Inspect `outputs/buyer_composability_demo.json` for the buyer-agent pre-spend gate, A2A correlation ID, downstream purchase decision, and reserved live CAP/payment fields.
Inspect `outputs/live_commerce_evidence.json` for the payment authorization checklist, AP2-style intent fields, x402 payment states, TAP-style identity/intent fields, CAP lifecycle capture slots, and offline-vs-live report hash comparison rule.
Inspect `outputs/judge_bundle.json` for one bundled artifact that includes the report, mock CAP transcript, local git evidence, public-head freshness status, unit-test results, and hashes for the generated judge artifacts.
Inspect `outputs/dorahacks_demo_package.md` for paste-ready BUIDL copy, a 5-minute recording runbook, screenshot checklist, source/hash block, and the credentialed live-proof slot that remains blocked until CROO dashboard/payment credentials exist.

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

## Requester Demo Harness

`trustbrief_agent/requester_harness.py` gives judges and buyer-agent reviewers a requester-side packet for the same sample payload:

- validates the request against `service_schema.json`
- previews the deterministic report hash and mock CAP lifecycle for that exact request
- emits explicit gate checks, blocked reasons, provider launch details, and the exact live proof artifacts to capture when CROO credentials are absent

This makes the handoff between "judge sees the request" and "provider returns the deliverable" much easier to explain without claiming a live paid order.

## Buyer Composability Proof

`trustbrief_agent/buyer_composability.py` shows the A2A commerce use case around TrustBrief:

- a buyer agent prepares a downstream purchase intent
- the buyer calls TrustBrief as a pre-spend verification dependency
- the proof packet carries one correlation ID across request hash, mock CAP order, report hash, and purchase gate
- live CAP/payment fields are reserved but left empty until real credentials, funding, and authorization exist

This demonstrates how TrustBrief can sit inside another agent's purchasing workflow without pretending that an offline run is a live paid order.

## Live Commerce Evidence Manifest

`trustbrief_agent/live_commerce_evidence.py` reserves the exact proof fields for the first credentialed CROO order:

- Agent Store listing URL, provider service ID, provider online evidence, requester agent ID, and funding confirmation
- payment authorization checklist with explicit human approval and max spend
- CAP `Negotiate -> Lock -> Deliver -> Clear` IDs, timestamps, payment/escrow hashes, delivery hash, and settlement status
- AP2-style intent fields, A2A x402-style payment states, and TAP-style identity/intent fields
- offline preview report hash vs live delivered report hash comparison
- screenshot and video capture checklist

The manifest is declarative. It does not perform wallet actions, submit to DoraHacks, or claim a live CROO order.

## Judge Bundle

`trustbrief_agent/evidence_bundle.py` packages the main judge-visible proof into one JSON artifact:

- the deterministic report from `trustbrief_agent.cli`
- the mock CAP lifecycle transcript from `trustbrief_agent.mock_cap_harness`
- the requester-side validation packet from `trustbrief_agent.requester_harness`
- the A2A buyer-composability packet from `trustbrief_agent.buyer_composability`
- the live-commerce evidence manifest from `trustbrief_agent.live_commerce_evidence`
- focused validation evidence from `python3 -m unittest discover -s tests -p 'test_*.py'`
- `service_schema.json` plus hashes of README/demo/submission assets
- hashes of the freshly generated report and mock transcript artifacts
- local git branch, commit, remote, and dirty-state evidence
- optional public GitHub verification metadata plus a local-head vs public-head consistency check
- `artifact_freshness.fresh_for_public_demo`, which is only true when the bundle was generated from the verified public head and no tracked files were dirty

This makes it easier to attach one artifact to a demo folder or screen recording without claiming live CROO execution.

## DoraHacks Demo Package

`trustbrief_agent/submission_package.py` turns the judge bundle into the final submission-facing material:

- BUIDL copy for DoraHacks fields
- 5-minute demo runbook
- screenshot checklist
- source and hash block for the public repo, bundle, request, and report
- credentialed live-proof slot with the exact blocked reasons and proof targets

Generate it after `outputs/judge_bundle.json` is fresh:

```bash
python3 -m trustbrief_agent.submission_package \
  --bundle outputs/judge_bundle.json \
  --output outputs/dorahacks_demo_package.md \
  --json-output outputs/dorahacks_demo_package.json
```

The package is intentionally generated from evidence already present in `outputs/judge_bundle.json`; it does not submit to DoraHacks, perform wallet actions, or claim a live CROO paid order.

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
