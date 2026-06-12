# Rank-1 Strategy

This hackathon is a build/list/demo competition, so the rank-1 path is product completeness and CAP proof rather than leaderboard probing.

## Highest-Impact Moves

1. Publish the GitHub repo with MIT license and a clean README.
2. Register `TrustBrief CAP Verifier` in CROO Agent Store.
3. Configure the `Verified Research Brief` schema service from `service_schema.json`.
4. Run the live provider with the CROO SDK key until Agent Store shows Online.
5. Use a second requester agent to place a paid order and capture the order lifecycle.
6. Record a compact demo showing Agent Store listing, paid request, schema delivery, and report hash.
7. File the DoraHacks BUIDL with the GitHub repo, demo video, and integration notes.

## Judging Narrative

TrustBrief proves A2A composability because any agent can subcontract it for claim verification before spending money or trusting a listing. Its output is durable across agents because it is structured JSON with source hashes and a report hash.

## Submission Risk Register

| Risk | Mitigation |
| --- | --- |
| Agent Store login/API key required | Dashboard steps are isolated and documented. |
| DoraHacks WAF blocks automation | Submission copy is prepared for manual paste. |
| Python SDK requires 3.10+ | Offline demo works on Python 3.9; live CAP mode documents Python 3.10+. |
| LLM hallucination risk | LLM is optional; deterministic evidence ledger remains the source of truth. |
| Weak judge signal if no paid order shown | Use a second agent and USDC on Base to capture full negotiation/payment/delivery. |

