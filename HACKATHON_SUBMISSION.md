# CROO AI Agent Hackathon Submission Draft

## BUIDL Name

TrustBrief CAP Verifier

## One-Liner

A paid CROO Agent Store service that turns supplied sources and claims into auditable due-diligence briefs with provenance hashes, evidence snippets, risk flags, and CAP schema delivery.

## Tracks

- Research & Intelligence Agents
- Data & Verification Agents

## Problem

Autonomous agents need to hire other agents, vendors, or protocols, but most research outputs are hard to audit. A downstream agent needs source-level provenance, not just a persuasive paragraph.

## Solution

TrustBrief is a CAP-callable provider agent. A requester submits a topic, claims, and public URLs or pasted source text. TrustBrief fetches the sources, builds a SHA-256 source ledger, evaluates each claim, flags weak evidence, and returns a structured report that another agent can consume before purchasing, listing, or escalating work.

## CROO / CAP Integration

- Provider runtime uses the official Python SDK `AgentClient`.
- WebSocket listener handles `NEGOTIATION_CREATED` and `ORDER_PAID`.
- Provider accepts negotiations with `accept_negotiation`.
- Provider delivers the report with `deliver_order`.
- Deliverable can be `schema` or `text` through `TRUSTBRIEF_DELIVERABLE_MODE`.
- Agent Store service configuration is captured in `service_schema.json`.
- Offline lifecycle proof is captured by `trustbrief_agent/mock_cap_harness.py`, which replays accept-and-deliver flow without CROO secrets.
- Judge bundle proof is captured by `trustbrief_agent/evidence_bundle.py`, which packages the report, CAP transcript, service schema, and git evidence into one artifact.

## Repository

Public GitHub repo: https://github.com/vandit98/croo-trustbrief-agent

License: MIT.

## Demo Flow

1. Show `service_schema.json` and Agent Store settings.
2. Run local demo:

   ```bash
   python3 -m trustbrief_agent.evidence_bundle \
     examples/sample_request.json \
     --report-output outputs/demo_report.json \
     --mock-output outputs/mock_cap_demo.json \
     --output outputs/judge_bundle.json
   ```

3. Open `outputs/demo_report.json`, `outputs/mock_cap_demo.json`, and `outputs/judge_bundle.json`.
4. Point to `claim_assessments`, `source_ledger`, `risk_flags`, `proof.report_hash`, the mock `negotiation_id` -> `order_id` -> `tx_hash` lifecycle, and the bundle's repo plus validation evidence.
5. Show `trustbrief_agent/cap_provider.py` handling CROO negotiation and paid delivery.
6. Once dashboard credentials exist, start live provider:

   ```bash
   export CROO_API_URL="https://api.croo.network"
   export CROO_WS_URL="wss://api.croo.network/ws"
   export CROO_SDK_KEY="croo_sk_..."
   python3.10 -m trustbrief_agent.cap_provider
   ```

## Submission Requirement Checklist

| Requirement | Status | Evidence |
| --- | --- | --- |
| Listed on CROO Agent Store | Blocked by dashboard login/API key | Use `service_schema.json` |
| Integrated with CAP | Code + offline lifecycle proof ready | `trustbrief_agent/cap_provider.py`, `trustbrief_agent/mock_cap_harness.py` |
| Open source permissive license | Ready | `LICENSE` |
| Demo + README | Ready | `README.md`, `DEMO_SCRIPT.md` |
| BUIDL filed on DoraHacks | Blocked by DoraHacks human verification/login | This file contains submission copy |

## Differentiators for Judging

- A2A-first: structured output and report hashes are built for downstream agents.
- Paid service-shaped: clear unit, price, SLA, and schema requirements.
- Verifiable: every fetched source receives a SHA-256 ledger entry.
- Robust demo: no paid API key is needed for the core report.
- Judge-ready proof pack: one command refreshes the report, CAP transcript, test result, and artifact hashes.
- Optional LLM: model summary can be enabled, but the evidence report remains deterministic.
