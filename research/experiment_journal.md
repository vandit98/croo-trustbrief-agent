# TrustBrief CROO Hackathon Experiment Journal

Goal: win the CROO AI Agent Hackathon by improving the Agent Store listing, CAP proof, demo quality, A2A composability, and judge-facing evidence.

## Current State

- Public repo: https://github.com/vandit98/croo-trustbrief-agent
- Core agent: deterministic claim verification with source ledger and report hash
- CAP wrapper: `trustbrief_agent/cap_provider.py`
- Service config: `service_schema.json`
- Known blockers: CROO Agent Store registration/API key, live paid order capture, demo upload, DoraHacks BUIDL filing

## 2026-06-13 Run - Offline CAP Lifecycle Harness

### Chosen target

Improve CAP proof and demo quality by adding an offline requester/provider lifecycle harness that reuses the real provider handlers, then make the default sample request work without network access.

### Exact changes

- Refactored `trustbrief_agent/cap_provider.py` to expose reusable `build_delivery_request`, `handle_negotiation_created`, and `handle_order_paid` functions.
- Added `trustbrief_agent/mock_cap_harness.py` to simulate `NEGOTIATION_CREATED` -> `accept_negotiation` -> `ORDER_PAID` -> `deliver_order` and emit a judge-visible JSON transcript.
- Added unit coverage for delivery mode rendering, provider handler flow, and the mock CAP transcript in `tests/test_trustbrief.py`.
- Updated `examples/sample_request.json` to include inline source text while preserving CROO URLs, so the offline demo produces supported evidence instead of network failures.
- Updated `README.md`, `DEMO_SCRIPT.md`, and `HACKATHON_SUBMISSION.md` to include the mock CAP demo path and evidence story.

### Commands run

```bash
git status --short --branch
git remote -v
git ls-remote --heads origin
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m trustbrief_agent.cli examples/sample_request.json --output outputs/demo_report.json
python3 -m trustbrief_agent.mock_cap_harness examples/sample_request.json --output outputs/mock_cap_demo.json
```

### Results

- `python3 -m unittest discover -s tests -p 'test_*.py'` -> `Ran 7 tests ... OK`
- `outputs/demo_report.json` now shows 3 supported claims, 1 intentionally unsupported claim, `overall_evidence_score: 0.7693`, and report hash `eee79d44274d8c49ea588e6fd62cfb3ca992963c4733616b6789d601f8dcabfe`.
- `outputs/mock_cap_demo.json` now shows mock `negotiation_id=neg_mock_001`, `order_id=ord_mock_001`, `tx_hash=0xmockdeliver01`, `delivery_mode=schema`, and the same report hash as the delivered object.
- `git ls-remote --heads origin` failed with `Could not resolve host: github.com`, so public remote state could not be live-verified from this environment.

### Blockers

- No outbound network / DNS access from this environment, so GitHub public state, CROO docs fetches, and any real CROO Agent Store proof remain unverified here.
- No CROO credentials were present, so live provider startup and paid-order capture remain blocked.

### Next action

When network and CROO credentials are available, capture a real Agent Store online status plus one paid order using the same request payload, then replace the mock lifecycle artifact in the demo package with live screenshots/video and real tx/order IDs.
