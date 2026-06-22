from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

from .buyer_composability import build_buyer_composability_packet
from .core import analyze_request, canonical_json, sha256_text
from .mock_cap_harness import run_mock_cap_flow
from .requester_harness import build_requester_demo


def _read_payload(path: str) -> Dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("request JSON must decode to an object")
    return decoded


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _relative_to_repo(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _load_json(path: Path) -> Dict[str, Any]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("{} must decode to a JSON object".format(path))
    return decoded


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_artifact(path: Path, repo_root: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    return {
        "path": _relative_to_repo(path, repo_root),
        "sha256": sha256_text(raw),
        "bytes": len(raw.encode("utf-8")),
    }


def _capture_command(repo_root: Path, command: Sequence[str]) -> Dict[str, Any]:
    result = subprocess.run(
        list(command),
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout_lines = [line for line in result.stdout.splitlines() if line.strip()]
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    return {
        "command": " ".join(command),
        "exit_code": result.returncode,
        "passed": result.returncode == 0,
        "stdout_tail": stdout_lines[-12:],
        "stderr_tail": stderr_lines[-12:],
    }


def _build_artifact_freshness(
    *,
    commit: str,
    status_lines: Sequence[str],
    tracked_status_lines: Sequence[str],
    public_repo_state: Dict[str, Any],
) -> Dict[str, Any]:
    public_head_commit = public_repo_state.get("head_commit", "")
    public_head_verified = bool(public_head_commit)
    local_matches_public = public_head_commit == commit if public_head_verified else None
    tracked_files_dirty = bool(tracked_status_lines)
    untracked_files_present = any(line.startswith("?? ") for line in status_lines)
    fresh_for_public_demo = bool(local_matches_public) and not tracked_files_dirty

    if not public_head_verified:
        status = "public_head_unverified"
        summary = "Public GitHub head was not supplied, so the bundle cannot prove it matches the judge-visible repo."
    elif not local_matches_public:
        status = "public_head_mismatch"
        summary = "Regenerate after syncing to the verified public main head."
    elif tracked_files_dirty:
        status = "tracked_files_dirty"
        summary = "Commit or discard tracked changes, then regenerate the bundle for a clean public-head artifact."
    else:
        status = "fresh_public_head"
        summary = "Bundle was generated from the verified public head with no tracked-file drift."

    return {
        "status": status,
        "summary": summary,
        "public_head_verified": public_head_verified,
        "public_head_commit": public_head_commit,
        "local_commit": commit,
        "local_commit_matches_public_head": local_matches_public,
        "tracked_files_dirty": tracked_files_dirty,
        "untracked_files_present": untracked_files_present,
        "fresh_for_public_demo": fresh_for_public_demo,
        "regeneration_required": not fresh_for_public_demo,
    }


def build_evidence_bundle(
    request_payload: Dict[str, Any],
    *,
    request_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    analysis_now: Optional[dt.datetime] = None,
    report: Optional[Dict[str, Any]] = None,
    cap_transcript: Optional[Dict[str, Any]] = None,
    validation_results: Optional[Dict[str, Any]] = None,
    generated_artifact_paths: Optional[Iterable[Path]] = None,
    public_repo_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    repo_root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    analysis_now = analysis_now or dt.datetime.now(dt.timezone.utc)
    now_iso = analysis_now.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    service_schema_path = repo_root / "service_schema.json"
    readme_path = repo_root / "README.md"
    demo_script_path = repo_root / "DEMO_SCRIPT.md"
    submission_path = repo_root / "HACKATHON_SUBMISSION.md"

    report = report or analyze_request(request_payload, now=analysis_now, use_openai=False)
    cap_transcript = cap_transcript or asyncio.run(
        run_mock_cap_flow(request_payload, deliver_mode="schema", analysis_now=analysis_now)
    )

    status_lines = [line for line in _run_git(repo_root, "status", "--short").splitlines() if line.strip()]
    tracked_status_lines = [
        line for line in _run_git(repo_root, "status", "--short", "--untracked-files=no").splitlines() if line.strip()
    ]
    branch = _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    commit = _run_git(repo_root, "rev-parse", "HEAD")
    remote_origin = _run_git(repo_root, "remote", "get-url", "origin")
    public_repo_state = dict(public_repo_state or {})
    artifact_freshness = _build_artifact_freshness(
        commit=commit,
        status_lines=status_lines,
        tracked_status_lines=tracked_status_lines,
        public_repo_state=public_repo_state,
    )

    key_assets = []
    for path in (service_schema_path, readme_path, demo_script_path, submission_path):
        if not path.exists():
            continue
        key_assets.append(_file_artifact(path, repo_root))

    generated_artifacts = []
    for path in generated_artifact_paths or []:
        resolved = path if path.is_absolute() else (repo_root / path)
        if resolved.exists():
            generated_artifacts.append(_file_artifact(resolved, repo_root))

    requester_demo = build_requester_demo(
        request_payload,
        request_path=request_path,
        service_schema_path=service_schema_path,
        analysis_now=analysis_now,
    )
    buyer_composability = build_buyer_composability_packet(
        request_payload,
        request_path=request_path,
        requester_demo=requester_demo,
        service_schema_path=service_schema_path,
        analysis_now=analysis_now,
    )

    bundle: Dict[str, Any] = {
        "bundle_schema_version": "1.0.0",
        "generated_at": now_iso,
        "generator": "trustbrief_agent.evidence_bundle",
        "purpose": "Judge-visible offline evidence bundle for CROO TrustBrief CAP submission.",
        "request_summary": {
            "path": _relative_to_repo(request_path, repo_root) if request_path else "",
            "task": request_payload.get("task", ""),
            "subject": request_payload.get("subject", ""),
            "claim_count": len(request_payload.get("claims", []) or []),
            "source_count": len(request_payload.get("sources", []) or []),
        },
        "repo_state": {
            "root": str(repo_root),
            "branch": branch,
            "commit": commit,
            "remote_origin": remote_origin,
            "dirty": bool(status_lines),
            "status_short": status_lines,
            "tracked_dirty": bool(tracked_status_lines),
            "tracked_status_short": tracked_status_lines,
            "untracked_status_short": [line for line in status_lines if line.startswith("?? ")],
        },
        "public_repo_state": public_repo_state,
        "artifact_freshness": artifact_freshness,
        "judge_assets": {
            "service_schema": _load_json(service_schema_path),
            "service_schema_sha256": sha256_text(service_schema_path.read_text(encoding="utf-8")),
            "key_asset_hashes": key_assets,
            "generated_artifact_hashes": generated_artifacts,
        },
        "commands": {
            "tests": "python3 -m unittest discover -s tests -p 'test_*.py'",
            "report_demo": "python3 -m trustbrief_agent.cli examples/sample_request.json --output outputs/demo_report.json",
            "mock_cap_demo": "python3 -m trustbrief_agent.mock_cap_harness examples/sample_request.json --output outputs/mock_cap_demo.json",
            "requester_demo": "python3 -m trustbrief_agent.requester_harness examples/sample_request.json --output outputs/requester_demo.json",
            "buyer_composability_demo": "python3 -m trustbrief_agent.buyer_composability examples/sample_request.json --output outputs/buyer_composability_demo.json",
            "judge_bundle": "python3 -m trustbrief_agent.evidence_bundle examples/sample_request.json --output outputs/judge_bundle.json",
        },
        "validation": validation_results or {},
        "offline_proof": {
            "report": report,
            "mock_cap_transcript": cap_transcript,
            "requester_demo": requester_demo,
            "buyer_composability": buyer_composability,
            "consistency_checks": {
                "report_hash_matches_transcript": report["proof"]["report_hash"] == cap_transcript["report_summary"]["report_hash"],
                "source_bundle_hash_matches_transcript": report["proof"]["source_bundle_hash"] == cap_transcript["report_summary"]["source_bundle_hash"],
                "buyer_report_hash_matches_report": buyer_composability["correlation"]["trustbrief_report_hash"] == report["proof"]["report_hash"],
                "buyer_request_hash_matches_report_input": buyer_composability["correlation"]["report_input_hash"] == report["proof"]["input_hash"],
                "local_commit_matches_public_head": artifact_freshness["local_commit_matches_public_head"],
                "fresh_for_public_demo": artifact_freshness["fresh_for_public_demo"],
            },
        },
        "blocked_live_steps": [
            "CROO Agent Store dashboard registration requires valid human credentials.",
            "Paid-order proof requires CROO SDK credentials and live network access.",
            "DoraHacks filing remains a manual authenticated submission step.",
        ],
    }

    requester_blockers = bundle["offline_proof"]["requester_demo"]["live_order_readiness"]["blocked_reasons"]
    if requester_blockers:
        bundle["blocked_live_steps"].extend(requester_blockers)

    stable = dict(bundle)
    proof = {
        "bundle_hash": sha256_text(canonical_json(stable)),
        "report_hash": report["proof"]["report_hash"],
        "mock_tx_hash": cap_transcript["tx_hash"],
    }
    bundle["proof"] = proof
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a judge-visible offline evidence bundle for TrustBrief.")
    parser.add_argument("request", help="Path to request JSON.")
    parser.add_argument("--output", "-o", help="Write evidence bundle JSON to this path.")
    parser.add_argument("--repo-root", help="Optional repository root to inspect.", default="")
    parser.add_argument("--report-output", help="Optional path to also write the deterministic report JSON.")
    parser.add_argument("--mock-output", help="Optional path to also write the mock CAP transcript JSON.")
    parser.add_argument("--requester-output", help="Optional path to also write the requester demo JSON.")
    parser.add_argument("--buyer-output", help="Optional path to also write the A2A buyer-composability JSON.")
    parser.add_argument("--public-repo-url", help="Optional verified public repository URL.")
    parser.add_argument("--public-default-branch", help="Optional verified public default branch.")
    parser.add_argument("--public-visibility", help="Optional verified public repository visibility.")
    parser.add_argument("--public-head-commit", help="Optional verified public head commit SHA.")
    parser.add_argument("--public-head-url", help="Optional verified public head commit URL.")
    parser.add_argument("--public-verified-at", help="Optional ISO timestamp for the public repo verification.")
    parser.add_argument(
        "--public-verification-source",
        help="Optional note describing how public repo state was verified.",
        default="",
    )
    parser.add_argument("--skip-tests", action="store_true", help="Skip running unit tests while generating the bundle.")
    args = parser.parse_args()

    request_path = Path(args.request)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    payload = _read_payload(str(request_path))
    analysis_now = dt.datetime.now(dt.timezone.utc)
    report = analyze_request(payload, now=analysis_now, use_openai=False)
    cap_transcript = asyncio.run(run_mock_cap_flow(payload, deliver_mode="schema", analysis_now=analysis_now))

    generated_paths = []
    if args.report_output:
        report_output_path = Path(args.report_output)
        _write_json(report_output_path, report)
        generated_paths.append(report_output_path)
    if args.mock_output:
        mock_output_path = Path(args.mock_output)
        _write_json(mock_output_path, cap_transcript)
        generated_paths.append(mock_output_path)
    if args.requester_output:
        requester_output_path = Path(args.requester_output)
        requester_demo = build_requester_demo(payload, request_path=request_path, analysis_now=analysis_now)
        _write_json(requester_output_path, requester_demo)
        generated_paths.append(requester_output_path)
    if args.buyer_output:
        buyer_output_path = Path(args.buyer_output)
        requester_demo = build_requester_demo(payload, request_path=request_path, analysis_now=analysis_now)
        buyer_packet = build_buyer_composability_packet(
            payload,
            request_path=request_path,
            requester_demo=requester_demo,
            analysis_now=analysis_now,
        )
        _write_json(buyer_output_path, buyer_packet)
        generated_paths.append(buyer_output_path)

    validation_results = {}
    if not args.skip_tests:
        validation_results["tests"] = _capture_command(
            repo_root,
            ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        )

    public_repo_state = {
        "repository_url": args.public_repo_url,
        "default_branch": args.public_default_branch,
        "visibility": args.public_visibility,
        "head_commit": args.public_head_commit,
        "head_commit_url": args.public_head_url,
        "verified_at": args.public_verified_at,
        "verification_source": args.public_verification_source,
    }
    public_repo_state = {key: value for key, value in public_repo_state.items() if value}

    bundle = build_evidence_bundle(
        payload,
        request_path=request_path,
        repo_root=repo_root,
        analysis_now=analysis_now,
        report=report,
        cap_transcript=cap_transcript,
        validation_results=validation_results,
        generated_artifact_paths=generated_paths,
        public_repo_state=public_repo_state,
    )
    rendered = json.dumps(bundle, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
