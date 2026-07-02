from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _load_json(path: Path) -> Dict[str, Any]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("{} must decode to a JSON object".format(path))
    return decoded


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_dict(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def _dedupe(items: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _build_regeneration_commands(package: Dict[str, Any]) -> List[Dict[str, str]]:
    copy = _require_dict(package, "dorahacks_buidl_copy")
    source = _require_dict(package, "source_hash_block")
    repo_url = source.get("repository_url") or copy.get("repository_url", "")
    git_url = repo_url + ".git" if repo_url and not repo_url.endswith(".git") else repo_url
    public_head = source.get("public_head_commit") or "<verified-public-head-sha>"
    public_head_url = source.get("public_head_url") or (
        "{}/commit/{}".format(repo_url, public_head) if repo_url and public_head else "<verified-public-head-url>"
    )
    public_verified_at = source.get("public_verified_at") or "<verified-at-iso8601>"
    verification_source = "git ls-remote {} refs/heads/main".format(git_url or "<public-git-url>")

    return [
        {
            "name": "verify_public_head",
            "purpose": "Confirm the judge-visible main branch before regenerating proof artifacts.",
            "command": "GIT_TERMINAL_PROMPT=0 git ls-remote {} refs/heads/main".format(git_url or "<public-git-url>"),
        },
        {
            "name": "run_tests",
            "purpose": "Keep the generated proof tied to a focused passing validation run.",
            "command": "python3 -m unittest discover -s tests -p 'test_*.py'",
        },
        {
            "name": "regenerate_judge_bundle",
            "purpose": "Refresh the report, CAP transcript, listing kit, live-commerce manifest, tests, hashes, and public-head freshness.",
            "command": (
                "python3 -m trustbrief_agent.evidence_bundle examples/sample_request.json "
                "--report-output outputs/demo_report.json "
                "--mock-output outputs/mock_cap_demo.json "
                "--requester-output outputs/requester_demo.json "
                "--buyer-output outputs/buyer_composability_demo.json "
                "--live-commerce-output outputs/live_commerce_evidence.json "
                "--listing-kit-output outputs/agent_store_listing_kit.json "
                "--public-repo-url {repo_url} "
                "--public-default-branch main "
                "--public-visibility public "
                "--public-head-commit {public_head} "
                "--public-head-url {public_head_url} "
                "--public-verified-at {public_verified_at} "
                "--public-verification-source \"{verification_source}\" "
                "--output outputs/judge_bundle.json"
            ).format(
                repo_url=repo_url or "<public-repo-url>",
                public_head=public_head,
                public_head_url=public_head_url,
                public_verified_at=public_verified_at,
                verification_source=verification_source,
            ),
        },
        {
            "name": "regenerate_dorahacks_package",
            "purpose": "Refresh the long-form package that carries BUIDL copy, form values, capture plan, and live-proof blanks.",
            "command": (
                "python3 -m trustbrief_agent.submission_package "
                "--bundle outputs/judge_bundle.json "
                "--output outputs/dorahacks_demo_package.md "
                "--json-output outputs/dorahacks_demo_package.json"
            ),
        },
        {
            "name": "regenerate_capture_pack",
            "purpose": "Extract the compact recording and manual-submit checklist from the long-form package.",
            "command": (
                "python3 -m trustbrief_agent.demo_capture_pack "
                "--package outputs/dorahacks_demo_package.json "
                "--output outputs/demo_capture_pack.md "
                "--json-output outputs/demo_capture_pack.json"
            ),
        },
    ]


def build_demo_capture_pack(package: Dict[str, Any], *, package_path: Optional[Path] = None) -> Dict[str, Any]:
    source_bundle = _require_dict(package, "source_bundle")
    readiness = _require_dict(package, "dorahacks_submission_readiness")
    capture_plan = _require_dict(package, "judge_demo_capture_plan")
    publish_gate = _require_dict(capture_plan, "publish_gate")
    source_hash_block = _require_dict(package, "source_hash_block")
    listing_kit = _require_dict(package, "agent_store_listing_kit")
    live_slot = _require_dict(package, "credentialed_live_proof_slot")

    shot_list = [shot for shot in capture_plan.get("shot_list", []) or [] if isinstance(shot, dict)]
    listing_screenshots = [
        shot for shot in listing_kit.get("screenshot_files", []) or [] if isinstance(shot, dict)
    ]
    form_values = [item for item in readiness.get("form_values", []) or [] if isinstance(item, dict)]
    live_blanks = [
        item for item in readiness.get("leave_blank_until_live_proof", []) or [] if isinstance(item, dict)
    ]
    live_blank_form_fields = [
        {
            "field": item.get("field", ""),
            "status": item.get("status", ""),
            "source": item.get("source", ""),
        }
        for item in form_values
        if str(item.get("status", "")).startswith("leave_blank")
    ]

    manual_steps = [str(item) for item in readiness.get("manual_submission_steps", []) or [] if item]
    final_checklist = _dedupe(
        [
            "Log in to DoraHacks with the authorized account.",
            "Record or upload the five-minute video that follows recording_sequence in order.",
            "Paste form values marked ready_to_paste into the BUIDL form.",
            "Leave live proof fields blank unless real Agent Store and CAP payment evidence exists.",
            *manual_steps,
            "Review do_not_claim guardrails before final submit.",
        ]
    )

    ready_to_record = bool(
        source_bundle.get("fresh_for_public_demo")
        and publish_gate.get("ready_for_offline_demo")
        and readiness.get("status") == "ready_for_offline_buidl_draft"
    )

    return {
        "demo_capture_pack_schema_version": "1.0.0",
        "source_package": {
            "path": str(package_path) if package_path else "",
            "generated_at": source_bundle.get("generated_at", ""),
            "freshness_status": source_bundle.get("freshness_status", ""),
            "fresh_for_public_demo": source_bundle.get("fresh_for_public_demo", False),
        },
        "ready_to_record": ready_to_record,
        "recording_goal": capture_plan.get("recording_goal", ""),
        "regeneration_commands": _build_regeneration_commands(package),
        "five_minute_voiceover": package.get("five_minute_runbook", []),
        "recording_sequence": [
            {
                "time": shot.get("time", ""),
                "screenshot_file": shot.get("file_name", ""),
                "screen": shot.get("screen", ""),
                "must_show": shot.get("must_show", []),
                "spoken_claim": shot.get("spoken_claim", ""),
            }
            for shot in shot_list
        ],
        "screenshot_filenames": {
            "capture_plan": [shot.get("file_name", "") for shot in shot_list if shot.get("file_name")],
            "agent_store_listing": [
                shot.get("file_name", "") for shot in listing_screenshots if shot.get("file_name")
            ],
        },
        "dorahacks_form_values": form_values,
        "source_hash_block": source_hash_block,
        "live_proof_blanks": {
            "form_fields": live_blank_form_fields,
            "evidence_required": live_blanks,
        },
        "manual_login_video_upload_checklist": final_checklist,
        "blocked_live_proof": {
            "ready_to_attempt": live_slot.get("ready_to_attempt", False),
            "blocked_reasons": live_slot.get("blocked_reasons", []),
            "proof_targets": live_slot.get("proof_targets", []),
        },
        "safety_guardrails": {
            "safe_spoken_claims": capture_plan.get("safe_spoken_claims", []),
            "do_not_claim": capture_plan.get("do_not_claim", []),
            "no_wallet_or_submission_action": True,
        },
    }


def render_demo_capture_markdown(pack: Dict[str, Any]) -> str:
    source_package = _require_dict(pack, "source_package")
    live_blanks = _require_dict(pack, "live_proof_blanks")
    blocked = _require_dict(pack, "blocked_live_proof")
    guardrails = _require_dict(pack, "safety_guardrails")
    screenshots = _require_dict(pack, "screenshot_filenames")
    source_hash_block = _require_dict(pack, "source_hash_block")

    lines = [
        "# TrustBrief Demo Capture Pack",
        "",
        "- Ready to record: {}".format(pack.get("ready_to_record", False)),
        "- Source package: {}".format(source_package.get("path", "")),
        "- Bundle freshness: {} (fresh_for_public_demo={})".format(
            source_package.get("freshness_status", ""),
            source_package.get("fresh_for_public_demo", False),
        ),
        "",
        "## Recording Goal",
        "",
        str(pack.get("recording_goal", "")),
        "",
        "## Regeneration Commands",
        "",
    ]

    for item in pack.get("regeneration_commands", []) or []:
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                "### {}".format(item.get("name", "")),
                "",
                str(item.get("purpose", "")),
                "",
                "```bash",
                str(item.get("command", "")),
                "```",
                "",
            ]
        )

    lines.extend(["## Five-Minute Voiceover", ""])
    for item in pack.get("five_minute_voiceover", []) or []:
        if not isinstance(item, dict):
            continue
        lines.append("- {} - {}: {}".format(item.get("time", ""), item.get("screen", ""), item.get("show", "")))

    lines.extend(["", "## Recording Sequence", ""])
    for item in pack.get("recording_sequence", []) or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "- {} - {} ({}): {}".format(
                item.get("screenshot_file", ""),
                item.get("screen", ""),
                item.get("time", ""),
                "; ".join(item.get("must_show", []) or []),
            )
        )
        if item.get("spoken_claim"):
            lines.append("  - Spoken claim: {}".format(item.get("spoken_claim", "")))

    lines.extend(["", "## Screenshot Files", ""])
    lines.append("- Capture plan: {}".format(", ".join(screenshots.get("capture_plan", []) or [])))
    lines.append("- Agent Store listing: {}".format(", ".join(screenshots.get("agent_store_listing", []) or [])))

    lines.extend(["", "## DoraHacks Form Values", ""])
    for item in pack.get("dorahacks_form_values", []) or []:
        if not isinstance(item, dict):
            continue
        value = item.get("value", "")
        if isinstance(value, list):
            value = ", ".join(str(part) for part in value)
        lines.append("- [{}] {}: {}".format(item.get("status", ""), item.get("field", ""), value))

    lines.extend(
        [
            "",
            "## Source And Hash Block",
            "",
            "- Repository: {}".format(source_hash_block.get("repository_url", "")),
            "- Local commit: {}".format(source_hash_block.get("local_commit", "")),
            "- Public head: {}".format(source_hash_block.get("public_head_commit", "")),
            "- Bundle hash: {}".format(source_hash_block.get("bundle_hash", "")),
            "- Report hash: {}".format(source_hash_block.get("report_hash", "")),
            "- Request input hash: {}".format(source_hash_block.get("request_input_hash", "")),
            "- Buyer correlation ID: {}".format(source_hash_block.get("buyer_correlation_id", "")),
            "- Live commerce manifest hash: {}".format(source_hash_block.get("live_commerce_manifest_hash", "")),
            "- Agent Store listing kit hash: {}".format(source_hash_block.get("agent_store_listing_kit_hash", "")),
            "- Tests passed: {}".format(source_hash_block.get("tests_passed", "")),
            "",
            "## Live-Proof Blanks",
            "",
        ]
    )
    for item in live_blanks.get("form_fields", []) or []:
        if not isinstance(item, dict):
            continue
        lines.append("- [{}] {}: {}".format(item.get("status", ""), item.get("field", ""), item.get("source", "")))
    for item in live_blanks.get("evidence_required", []) or []:
        if not isinstance(item, dict):
            continue
        lines.append("- Evidence required for {}: {}".format(item.get("field", ""), item.get("required_evidence", "")))

    lines.extend(["", "## Manual Login And Upload Checklist", ""])
    for item in pack.get("manual_login_video_upload_checklist", []) or []:
        lines.append("- {}".format(item))

    lines.extend(["", "## Blocked Live Proof", ""])
    lines.append("- Ready to attempt: {}".format(blocked.get("ready_to_attempt", False)))
    lines.append("- Proof targets: {}".format(", ".join(blocked.get("proof_targets", []) or [])))
    for reason in blocked.get("blocked_reasons", []) or []:
        lines.append("- Blocked reason: {}".format(reason))

    lines.extend(["", "## Safety Guardrails", "", "### Safe Spoken Claims", ""])
    for item in guardrails.get("safe_spoken_claims", []) or []:
        lines.append("- {}".format(item))

    lines.extend(["", "### Do Not Claim", ""])
    for item in guardrails.get("do_not_claim", []) or []:
        lines.append("- {}".format(item))
    lines.append("- No wallet action, DoraHacks submission, or live CROO order is performed by this generator.")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a compact TrustBrief recording and manual-submit capture pack.")
    parser.add_argument(
        "--package",
        default="outputs/dorahacks_demo_package.json",
        help="Path to outputs/dorahacks_demo_package.json or an equivalent package JSON.",
    )
    parser.add_argument("--output", "-o", help="Optional Markdown output path.")
    parser.add_argument("--json-output", help="Optional JSON output path.")
    args = parser.parse_args()

    package_path = Path(args.package)
    package = _load_json(package_path)
    pack = build_demo_capture_pack(package, package_path=package_path)
    rendered = render_demo_capture_markdown(pack)
    if args.output:
        _write_text(Path(args.output), rendered)
    if args.json_output:
        _write_json(Path(args.json_output), pack)
    if not args.output and not args.json_output:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
