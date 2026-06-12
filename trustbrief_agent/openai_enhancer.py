from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def _extract_text(response: Dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"].strip()
    chunks = []
    for item in response.get("output", []) or []:
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def enhance_report(report: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "OPENAI_API_KEY is not set"}

    model = os.environ.get("TRUSTBRIEF_OPENAI_MODEL", "gpt-5.5")
    prompt = {
        "subject": report.get("subject"),
        "recommendation": report.get("recommendation"),
        "overall_evidence_score": report.get("overall_evidence_score"),
        "claim_assessments": report.get("claim_assessments", [])[:8],
        "risk_flags": report.get("risk_flags", [])[:8],
    }
    body = {
        "model": model,
        "reasoning": {"effort": "low"},
        "instructions": (
            "You are a concise verification analyst. Return a judge-ready summary "
            "in under 140 words. Do not invent sources or claims."
        ),
        "input": json.dumps(prompt, sort_keys=True),
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer {}".format(api_key),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        return {"status": "error", "model": model, "error": "HTTP {}: {}".format(exc.code, error_body[:500])}
    except urllib.error.URLError as exc:
        return {"status": "error", "model": model, "error": str(exc)}

    text = _extract_text(parsed)
    return {
        "status": "ok" if text else "empty",
        "model": model,
        "summary": text,
        "response_id": parsed.get("id", ""),
    }

