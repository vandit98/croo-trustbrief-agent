from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

from .core import analyze_request, canonical_json, sha256_text
from .mock_cap_harness import run_mock_cap_flow


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
    branch = _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    commit = _run_git(repo_root, "rev-parse", "HEAD")
    remote_origin = _run_git(repo_root, "remote", "get-url", "origin")

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
        },
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
            "judge_bundle": "python3 -m trustbrief_agent.evidence_bundle examples/sample_request.json --output outputs/judge_bundle.json",
        },
        "validation": validation_results or {},
        "offline_proof": {
            "report": report,
            "mock_cap_transcript": cap_transcript,
            "consistency_checks": {
                "report_hash_matches_transcript": report["proof"]["report_hash"] == cap_transcript["report_summary"]["report_hash"],
                "source_bundle_hash_matches_transcript": report["proof"]["source_bundle_hash"] == cap_transcript["report_summary"]["source_bundle_hash"],
            },
        },
        "blocked_live_steps": [
            "CROO Agent Store dashboard registration requires valid human credentials.",
            "Paid-order proof requires CROO SDK credentials and live network access.",
            "DoraHacks filing remains a manual authenticated submission step.",
        ],
    }

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

    validation_results = {}
    if not args.skip_tests:
        validation_results["tests"] = _capture_command(
            repo_root,
            ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        )

    bundle = build_evidence_bundle(
        payload,
        request_path=request_path,
        repo_root=repo_root,
        analysis_now=analysis_now,
        report=report,
        cap_transcript=cap_transcript,
        validation_results=validation_results,
        generated_artifact_paths=generated_paths,
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
