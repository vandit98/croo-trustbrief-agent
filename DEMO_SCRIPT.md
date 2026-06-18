# Demo Script - Under 5 Minutes

## 0:00-0:30 - Hook

"TrustBrief is a CROO Agent Store service for agents that need to verify claims before they hire another agent, buy a service, or trust a marketplace listing."

## 0:30-1:20 - Service Setup

Show `service_schema.json`.

- service name: `Verified Research Brief`
- price: `1 USDC`
- SLA: `20 minutes`
- requirements: schema with task, subject, claims, and sources
- deliverable: schema report

## 1:20-2:20 - Offline Report

Run:

```bash
python3 -m trustbrief_agent.evidence_bundle \
  examples/sample_request.json \
  --report-output outputs/demo_report.json \
  --mock-output outputs/mock_cap_demo.json \
  --requester-output outputs/requester_demo.json \
  --public-head-commit <verified-public-head-sha> \
  --public-head-url https://github.com/vandit98/croo-trustbrief-agent/commit/<verified-public-head-sha> \
  --public-verified-at <verified-at-iso8601> \
  --public-verification-source "GitHub connector" \
  --output outputs/judge_bundle.json
```

Open the report and show:

- `recommendation`
- `claim_assessments`
- `source_ledger`
- `risk_flags`
- `proof.report_hash`
- `mock_cap_demo.json` showing mock `negotiation_id`, `order_id`, and `tx_hash`
- `requester_demo.json` showing request-schema validation, live-order gate checks, provider launch command, and the exact proof artifacts still needed from CROO
- `judge_bundle.json` showing the combined proof package, generated artifact hashes, unit-test pass result, and current repo commit
- `judge_bundle.json.public_repo_state` showing the verified public `main` head and whether the local bundle matches it

## 2:20-3:20 - CAP Provider Code

Show `trustbrief_agent/cap_provider.py`.

Explain:

- `NEGOTIATION_CREATED` triggers `accept_negotiation`
- `ORDER_PAID` triggers source verification
- `deliver_order` sends a schema deliverable back through CROO
- the offline mock harness reuses the same provider handlers for judge-visible proof without CROO secrets

## 3:20-4:20 - Why Agents Pay for It

"A buyer agent can call TrustBrief as a dependency before making a purchase. The output is not just a summary; it is a machine-readable provenance object with source hashes and claim-level evidence."

## 4:20-5:00 - Close

"The core works without secrets. To go live, register the provider in CROO Agent Store, paste the schema from this repo, set the SDK key, and start the provider. From there every paid request settles through CAP."
