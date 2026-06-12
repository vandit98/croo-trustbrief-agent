from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .core import analyze_request


def _read_payload(path: str) -> Any:
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a TrustBrief verification request.")
    parser.add_argument("request", help="Path to request JSON, or '-' for stdin.")
    parser.add_argument("--output", "-o", help="Write report JSON to this path.")
    parser.add_argument("--use-openai", action="store_true", help="Use optional OpenAI summary enhancement.")
    args = parser.parse_args()

    report = analyze_request(_read_payload(args.request), use_openai=args.use_openai)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

