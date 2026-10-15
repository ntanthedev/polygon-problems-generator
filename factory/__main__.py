"""Factory CLI — ingestion, V1 spec and isolated C++17 solution checks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .spec import ProblemSpecError, from_polygon_folder, inspect_spec, parse_json
from .ingest import ingest_file


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

    ing = commands.add_parser("ingest", help="Import TXT, Markdown, PDF or image into a new V1 draft")
    ing.add_argument("source", type=Path, help="Path to original file, never modified")
    ing.add_argument("--slug", required=True, help="lowercase snake_case problem name")
    ing.add_argument("--dest", type=Path, help="New problem folder (default: problems/<slug>)")
    ing.add_argument("--language", default="und", help="BCP47 language or und for unknown")
    ing.add_argument("--idea", help="Optional user-provided algorithm idea")
    ing.add_argument("--solution-file", type=Path, help="Optional user source code (copied, never run)")
    ing.add_argument("--solution-language", choices=["cpp17", "java21", "python3", "other"],
                     default="cpp17")
    ing.add_argument("--vision-model", help="OPT-IN: send image/PDF pages to Gemini model ID (requires GEMINI_API_KEY)")

    sols = commands.add_parser("solutions", help="Check a user/agent solution against an independent oracle")
    sol_actions = sols.add_subparsers(dest="solution_action", required=True)
    verify = sol_actions.add_parser("verify", help="Run reviewed C++17 exact-output cases in Docker")
    verify.add_argument("problem_dir", type=Path, help="Folder containing reviewed spec.json")
    verify.add_argument("--candidate", type=Path, help="Candidate C++ source, otherwise guidance.solution.file")
    verify.add_argument("--oracle", type=Path, required=True, help="INDEPENDENT brute/reference C++ source")
    verify.add_argument("--tests-dir", type=Path, help="Optional folder of .in and optional .out cases")
    verify.add_argument("--timeout", type=float, default=2.0, help="Wall seconds per test (0.1–30)")
    verify.add_argument("--image", default="gcc:14", help="Locally available C++ Docker image; never auto-pulled")
    verify.add_argument("--report", type=Path, help="Create report JSON exclusively, refuse overwrites")

    args = p.parse_args(argv)
    try:
        if args.group == "solutions":
            from .solution_check import resolve_candidate, verify_candidate
            from .docker_runner import DockerRunner
            spec = parse_json((args.problem_dir / "spec.json").read_text(encoding="utf-8"))
            readiness = inspect_spec(spec, ready=True)
            if readiness["status"] != "PASS":
                issues = "; ".join(
                    f"{issue['code']}: {issue['message']}"
                    for issue in readiness["errors"]
                )
                raise ProblemSpecError("Spec is not reviewed/ready: " + issues)
            if spec["statement"]["outputPolicy"] != "exact":
                raise ProblemSpecError(
                    "SOL-001 supports exact-output C++17 only, not semantic/floating checker tasks"
                )
            candidate = resolve_candidate(args.problem_dir, spec, args.candidate)
            with DockerRunner(image=args.image) as isolated:
                report = verify_candidate(
                    spec, candidate=candidate, oracle=args.oracle,
                    test_dir=args.tests_dir, timeout_s=args.timeout, runner=isolated
                )
            serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
            if args.report:
                with args.report.open("x", encoding="utf-8") as output:
                    output.write(serialized)
                print(f"Saved solution agreement report to {args.report}")
            else:
                print(serialized, end="")
            return 0 if report["verdict"] == "PASS_ON_TESTS" else 1
        if args.group == "ingest":
            provider = None
            if args.vision_model:
                from .gemini_vision import GeminiVision
                provider = GeminiVision(args.vision_model)
            report = ingest_file(
                args.source, slug=args.slug, dest=args.dest or Path("problems") / args.slug,
                provider=provider, language=args.language, idea=args.idea,
                solution_file=args.solution_file,
                solution_language=args.solution_language,
            )
            print(json.dumps(report, indent=2, ensure_ascii=False))
            print("Draft created; review ambiguities and validate with --ready before proceeding.")
            return 0
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
