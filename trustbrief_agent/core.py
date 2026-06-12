from __future__ import annotations

import copy
import datetime as dt
import hashlib
import html
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


REPORT_SCHEMA_VERSION = "1.0.0"
DEFAULT_TIMEOUT_SECONDS = 12
MAX_SOURCE_BYTES = 750_000

STOPWORDS = {
    "about", "after", "again", "against", "also", "and", "any", "are", "because",
    "been", "before", "being", "between", "both", "but", "can", "could", "does",
    "all", "as", "at", "by", "each", "every", "for", "from", "has", "have",
    "in", "into", "its", "more", "not", "of", "on", "only", "or", "other",
    "over", "per", "should", "than", "that", "the", "their", "then", "there",
    "these", "they", "this", "through", "under", "use", "used", "using", "was",
    "were", "when", "where", "which", "while", "with", "within", "would", "your",
}


@dataclass
class SourceRecord:
    label: str
    url: str
    text: str
    title: str = ""
    error: str = ""
    fetched_at: str = ""
    sha256: str = ""

    def public_ledger(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "title": self.title,
            "url": self.url,
            "sha256": self.sha256,
            "text_characters": len(self.text),
            "fetched_at": self.fetched_at,
            "error": self.error,
        }


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._title_depth = 0
        self.title_parts: List[str] = []
        self.text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self._skip_depth += 1
        if tag == "title":
            self._title_depth += 1
        if tag in {"p", "br", "div", "section", "article", "li", "tr", "h1", "h2", "h3"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        if tag in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        data = data.strip()
        if not data:
            return
        if self._title_depth:
            self.title_parts.append(data)
        self.text_parts.append(data)
        self.text_parts.append(" ")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def compact_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\r\n?", "\n", value)
    value = re.sub(r"[ \t\f\v]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def tokenize(value: str) -> List[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", value.lower())
    return [word for word in words if word not in STOPWORDS]


def _decode_response(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([a-zA-Z0-9_-]+)", content_type or "")
    encodings = [match.group(1)] if match else []
    encodings.extend(["utf-8", "latin-1"])
    for encoding in encodings:
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def _html_to_text(raw: str) -> Tuple[str, str]:
    parser = _HTMLTextExtractor()
    parser.feed(raw)
    title = compact_text(" ".join(parser.title_parts))
    text = compact_text(" ".join(parser.text_parts))
    return title, text


def _fetch_url(url: str, timeout: int) -> Tuple[str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "TrustBrief-CAP-Verifier/0.1 (+https://github.com/)",
            "Accept": "text/html,text/plain,application/json,application/xml;q=0.9,*/*;q=0.5",
        },
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        body = response.read(MAX_SOURCE_BYTES + 1)
        if len(body) > MAX_SOURCE_BYTES:
            body = body[:MAX_SOURCE_BYTES]
        content_type = response.headers.get("content-type", "")
    decoded = _decode_response(body, content_type)
    if "html" in content_type.lower() or "<html" in decoded[:1000].lower():
        return _html_to_text(decoded)
    return "", compact_text(decoded)


def load_source(source: Any, now_iso: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> SourceRecord:
    if isinstance(source, str):
        source = {"url": source}
    if not isinstance(source, dict):
        source = {"label": "invalid source", "text": str(source), "url": ""}

    label = str(source.get("label") or source.get("title") or source.get("url") or "inline source")
    url = str(source.get("url") or source.get("path") or "")
    title = str(source.get("title") or "")
    text = ""
    error = ""

    try:
        if source.get("text"):
            text = compact_text(str(source.get("text")))
        elif source.get("url"):
            title_from_url, text = _fetch_url(url, timeout)
            title = title or title_from_url
        elif source.get("path"):
            with open(str(source["path"]), "r", encoding="utf-8") as handle:
                text = compact_text(handle.read())
        else:
            error = "source has no text, url, or path"
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        error = "{}: {}".format(exc.__class__.__name__, exc)

    return SourceRecord(
        label=label[:120],
        url=url,
        title=title[:160],
        text=text,
        error=error,
        fetched_at=now_iso,
        sha256=sha256_text(text) if text else "",
    )


def _split_sentences(text: str) -> List[str]:
    candidates = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [compact_text(candidate) for candidate in candidates if len(compact_text(candidate)) >= 40]


def critical_terms(value: str) -> List[str]:
    raw_terms = re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b|\b[A-Z0-9_]{2,}\b", value)
    return sorted(set(tokenize(" ".join(raw_terms))))


def _source_score(claim: str, claim_tokens: Sequence[str], source_text: str) -> Tuple[float, List[str], List[str], str]:
    if not claim_tokens or not source_text:
        return 0.0, [], [], ""
    source_tokens = set(tokenize(source_text))
    matched = sorted(set(claim_tokens).intersection(source_tokens))
    score = len(matched) / max(1, len(set(claim_tokens)))
    missing_critical = sorted([term for term in critical_terms(claim) if term not in source_tokens])
    if missing_critical:
        score = min(score, 0.22)

    best_sentence = ""
    best_sentence_score = -1
    for sentence in _split_sentences(source_text)[:300]:
        sentence_tokens = set(tokenize(sentence))
        sentence_score = len(set(claim_tokens).intersection(sentence_tokens))
        if sentence_score > best_sentence_score:
            best_sentence_score = sentence_score
            best_sentence = sentence
    return score, matched, missing_critical, best_sentence[:600]


def evaluate_claim(claim: str, sources: Sequence[SourceRecord]) -> Dict[str, Any]:
    claim_tokens = tokenize(claim)
    scored = []
    for source in sources:
        score, matched, missing_critical, snippet = _source_score(claim, claim_tokens, source.text)
        if score > 0:
            scored.append((score, source, matched, missing_critical, snippet))
    scored.sort(key=lambda item: item[0], reverse=True)

    best_score = scored[0][0] if scored else 0.0
    best_missing_critical = scored[0][3] if scored else []
    if not best_missing_critical and (best_score >= 0.55 or (scored and len(scored[0][2]) >= 5)):
        status = "supported"
    elif best_score >= 0.25 or (scored and len(scored[0][2]) >= 3 and not best_missing_critical):
        status = "partially_supported"
    else:
        status = "unsupported"

    evidence = []
    for score, source, matched, missing_critical, snippet in scored[:3]:
        evidence.append({
            "source_label": source.label,
            "source_url": source.url,
            "source_sha256": source.sha256,
            "overlap_score": round(score, 4),
            "matched_terms": matched[:16],
            "missing_critical_terms": missing_critical[:8],
            "snippet": snippet,
        })

    return {
        "claim": claim,
        "status": status,
        "confidence_score": round(best_score, 4),
        "evidence": evidence,
    }


def _risk_flags(claims: Sequence[Dict[str, Any]], sources: Sequence[SourceRecord]) -> List[Dict[str, str]]:
    flags: List[Dict[str, str]] = []
    usable_sources = [source for source in sources if source.text and not source.error]
    failed_sources = [source for source in sources if source.error]
    unsupported = [claim for claim in claims if claim["status"] == "unsupported"]
    partial = [claim for claim in claims if claim["status"] == "partially_supported"]

    if not usable_sources:
        flags.append({"severity": "high", "code": "no_usable_sources", "message": "No source text was available for verification."})
    elif len(usable_sources) == 1:
        flags.append({"severity": "medium", "code": "single_source", "message": "Only one usable source was available; independent corroboration is weak."})
    if failed_sources:
        flags.append({"severity": "medium", "code": "source_fetch_failures", "message": "{} source(s) could not be fetched.".format(len(failed_sources))})
    if unsupported:
        flags.append({"severity": "high", "code": "unsupported_claims", "message": "{} claim(s) had no clear supporting evidence.".format(len(unsupported))})
    if partial:
        flags.append({"severity": "medium", "code": "partial_support", "message": "{} claim(s) were only partially supported.".format(len(partial))})
    if claims and len([claim for claim in claims if claim["status"] == "supported"]) / float(len(claims)) < 0.5:
        flags.append({"severity": "medium", "code": "low_evidence_density", "message": "Fewer than half of the claims were strongly supported."})
    return flags


def _recommendation(flags: Sequence[Dict[str, str]]) -> str:
    high = [flag for flag in flags if flag["severity"] == "high"]
    medium = [flag for flag in flags if flag["severity"] == "medium"]
    if high:
        return "needs_review"
    if medium:
        return "usable_with_caveats"
    return "ready"


def _brief_summary(subject: str, claim_results: Sequence[Dict[str, Any]], flags: Sequence[Dict[str, str]]) -> str:
    supported = len([claim for claim in claim_results if claim["status"] == "supported"])
    partial = len([claim for claim in claim_results if claim["status"] == "partially_supported"])
    unsupported = len([claim for claim in claim_results if claim["status"] == "unsupported"])
    if not claim_results:
        return "TrustBrief collected sources for {} and produced a provenance ledger, but no explicit claims were provided.".format(subject or "the requested topic")
    return (
        "TrustBrief evaluated {total} claim(s) for {subject}: {supported} supported, "
        "{partial} partially supported, and {unsupported} unsupported."
    ).format(
        total=len(claim_results),
        subject=subject or "the requested topic",
        supported=supported,
        partial=partial,
        unsupported=unsupported,
    )


def _coerce_request(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
            if isinstance(decoded, dict):
                return decoded
        except json.JSONDecodeError:
            return {"task": payload, "subject": payload[:120], "claims": [], "sources": []}
    if isinstance(payload, dict):
        return payload
    return {"task": str(payload), "subject": "ad hoc request", "claims": [], "sources": []}


def analyze_request(payload: Any, now: Optional[dt.datetime] = None, use_openai: bool = False) -> Dict[str, Any]:
    request = _coerce_request(payload)
    now = now or dt.datetime.now(dt.timezone.utc)
    now_iso = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    subject = str(request.get("subject") or request.get("topic") or request.get("task") or "requested topic")[:180]
    task = str(request.get("task") or "Verify supplied claims against supplied sources.")
    claims = [str(claim).strip() for claim in request.get("claims", []) if str(claim).strip()]
    sources_input = request.get("sources", [])
    if not isinstance(sources_input, list):
        sources_input = [sources_input]
    max_sources = int(request.get("max_sources") or 6)

    sources = [load_source(source, now_iso) for source in sources_input[:max_sources]]
    claim_results = [evaluate_claim(claim, sources) for claim in claims]
    flags = _risk_flags(claim_results, sources)
    supported_scores = [claim["confidence_score"] for claim in claim_results]
    evidence_score = round(sum(supported_scores) / len(supported_scores), 4) if supported_scores else 0.0

    request_public = copy.deepcopy(request)
    if "sources" in request_public:
        request_public["sources"] = [
            {key: value for key, value in source.items() if key != "text"} if isinstance(source, dict) else source
            for source in request_public["sources"]
        ]

    report: Dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "agent": "TrustBrief CAP Verifier",
        "generated_at": now_iso,
        "subject": subject,
        "task": task,
        "recommendation": _recommendation(flags),
        "executive_summary": _brief_summary(subject, claim_results, flags),
        "overall_evidence_score": evidence_score,
        "claim_assessments": claim_results,
        "risk_flags": flags,
        "source_ledger": [source.public_ledger() for source in sources],
        "a2a_contract": {
            "deliverable_type": "schema",
            "priced_unit": "one verified research brief",
            "expected_sla_minutes": 20,
            "downstream_use": [
                "agent due diligence",
                "marketplace listing checks",
                "claim provenance before autonomous purchasing",
            ],
        },
        "request": request_public,
    }

    if use_openai:
        try:
            from .openai_enhancer import enhance_report

            report["llm_enhancement"] = enhance_report(report)
        except Exception as exc:  # pragma: no cover - defensive optional path
            report["llm_enhancement"] = {"status": "error", "error": "{}: {}".format(exc.__class__.__name__, exc)}
    else:
        report["llm_enhancement"] = {"status": "disabled"}

    source_bundle_hash = sha256_text(canonical_json([
        {"url": source.url, "sha256": source.sha256, "error": source.error}
        for source in sources
    ]))
    stable_for_hash = copy.deepcopy(report)
    stable_for_hash.pop("generated_at", None)
    proof = {
        "input_hash": sha256_text(canonical_json(request_public)),
        "source_bundle_hash": source_bundle_hash,
        "report_hash": sha256_text(canonical_json(stable_for_hash)),
        "algorithm": "trustbrief-v1 lexical evidence overlap with source sha256 ledger",
    }
    report["proof"] = proof
    return report
