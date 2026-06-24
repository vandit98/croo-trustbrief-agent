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
  --buyer-output outputs/buyer_composability_demo.json \
  --live-commerce-output outputs/live_commerce_evidence.json \
  --public-head-commit <verified-public-head-sha> \
  --public-head-url https://github.com/vandit98/croo-trustbrief-agent/commit/<verified-public-head-sha> \
  --public-verified-at <verified-at-iso8601> \
  --public-verification-source "GitHub connector" \
  --output outputs/judge_bundle.json

python3 -m trustbrief_agent.submission_package \
  --bundle outputs/judge_bundle.json \
  --output outputs/dorahacks_demo_package.md \
  --json-output outputs/dorahacks_demo_package.json
```

Open the report and show:

- `dorahacks_demo_package.md` showing the BUIDL copy, 5-minute recording sequence, screenshot checklist, source/hash block, and credentialed live-proof slot
- `recommendation`
- `claim_assessments`
- `source_ledger`
- `risk_flags`
- `proof.report_hash`
- `mock_cap_demo.json` showing mock `negotiation_id`, `order_id`, and `tx_hash`
- `requester_demo.json` showing request-schema validation, live-order gate checks, provider launch command, and the exact proof artifacts still needed from CROO
- `buyer_composability_demo.json` showing the buyer-agent correlation ID, TrustBrief report hash, downstream purchase decision, and reserved live CAP/payment fields
- `live_commerce_evidence.json` showing payment authorization status, CAP lifecycle slots, x402 payment states, TAP identity/intent fields, and the offline-vs-live report hash comparison rule
- `judge_bundle.json` showing the combined proof package, generated artifact hashes, unit-test pass result, and current repo commit
- `judge_bundle.json.public_repo_state` plus `artifact_freshness` showing the verified public `main` head, whether tracked files were dirty, and whether the bundle is fresh for the public demo

## 2:20-3:20 - CAP Provider Code

Show `trustbrief_agent/cap_provider.py`.

Explain:

- `NEGOTIATION_CREATED` triggers `accept_negotiation`
- `ORDER_PAID` triggers source verification
- `deliver_order` sends a schema deliverable back through CROO
- the offline mock harness reuses the same provider handlers for judge-visible proof without CROO secrets

## 3:20-4:20 - Why Buyer Agents Pay for It

"A buyer agent can call TrustBrief as a dependency before making a purchase. The output is not just a summary; it is a machine-readable provenance object with source hashes and claim-level evidence."

Show `outputs/buyer_composability_demo.json` and `outputs/live_commerce_evidence.json`.

- `correlation.correlation_id`
- `correlation.trustbrief_report_hash`
- `downstream_decision.decision`
- `live_cap_placeholders.payment_state`
- `cap_lifecycle` phases for `Negotiate`, `Lock`, `Deliver`, and `Clear`
- `payment_authorization.status`
- `hash_comparison.match_status`

## 4:20-5:00 - Close

"The core works without secrets. To go live, register the provider in CROO Agent Store, paste the schema from this repo, set the SDK key, and start the provider. From there every paid request settles through CAP, and the buyer packet is where the live order IDs, delivery tx hash, and downstream decision proof will land."
