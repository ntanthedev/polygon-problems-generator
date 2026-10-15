"""Factory CLI (offline spec operations only in ING-001)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .spec import ProblemSpecError, from_polygon_folder, inspect_spec, parse_json


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m factory", description="Offline Polygon Factory tools")
    commands = p.add_subparsers(dest="group", required=True)
    sp = commands.add_parser("spec", help="Normalized problem specification V1")
    actions = sp.add_subparsers(dest="action", required=True)
    check = actions.add_parser("validate", help="Validate JSON structure (and optional readiness)")
    check.add_argument("file", type=Path)
    check.add_argument("--ready", action="store_true", help="Require all information needed for test generation")
    check.add_argument("--json", action="store_true", help="Emit machine-readable validation report")

    convert = actions.add_parser("from-local", help="Make draft from existing Polygon statement/samples")
    convert.add_argument("problem_dir", type=Path)
    group = convert.add_mutually_exclusive_group()
    group.add_argument("--idea", help="User-provided algorithm idea (literal text)")
    group.add_argument("--idea-file", help="Project-relative path to idea text file")
    convert.add_argument("--solution-file", help="Project-relative path to user solution")
    convert.add_argument("--solution-language", default="cpp17",
                         choices=["cpp17", "java21", "python3", "other"])
    convert.add_argument("--output", type=Path, help="Create JSON file; never overwrite an existing one")

    args = p.parse_args(argv)
    try:
        if args.action == "validate":
            payload = parse_json(args.file.read_text(encoding="utf-8"))
            report = inspect_spec(payload, ready=args.ready)
            if args.json:
                print(json.dumps(report, indent=2, ensure_ascii=False))
            else:
                print(f"Problem spec {report['status']} (ready={args.ready}): {args.file}")
                for item in report["errors"]:
                    print(f"  ERROR [{item['code']}] {item['path']}: {item['message']}")
                for item in report["warnings"]:
                    print(f"  WARN  [{item['code']}] {item['path']}: {item['message']}")
            return 0 if report["status"] == "PASS" else 1
        spec = from_polygon_folder(
            args.problem_dir, idea=args.idea, idea_file=args.idea_file,
            solution_file=args.solution_file, solution_language=args.solution_language,
        )
        text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
        if args.output is None:
            print(text, end="")
        else:
            # Exclusive file creation; never silently overwrite a user's spec.
            with args.output.open("x", encoding="utf-8") as dest:
                dest.write(text)
            print(f"Draft spec written to {args.output} (not ready until reviewed)")
        return 0
    except (ProblemSpecError, OSError, UnicodeError) as exc:
        print(f"Factory spec error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
