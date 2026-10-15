"""CLI entry point: python -m polyup <problem>"""

import argparse
import json
import os
import sys
from pathlib import Path

from .access import collect_access
from .api import PolygonAPI, PolygonAPIError
from .config import SyncConfig
from .sync import grant_access, list_accesses, sync_problem
from .sync_plan import UnsafeSyncError, build_sync_plan


def _load_env(env_file: Path):
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _exit_on_api_error(exc: PolygonAPIError):
    print(f"  {exc}", file=sys.stderr)
    sys.exit(1)


def _api(repo_root: Path, delay: float) -> PolygonAPI:
    _load_env(repo_root / ".env")
    api_key = os.environ.get("POLYGON_API_KEY")
    api_secret = os.environ.get("POLYGON_API_SECRET")
    if not api_key or not api_secret:
        print("Set POLYGON_API_KEY and POLYGON_API_SECRET in .env file.", file=sys.stderr)
        sys.exit(1)
    return PolygonAPI(api_key, api_secret, delay=delay)


def _problem_dir(repo_root: Path, name: str) -> Path:
    problem_dir = repo_root / "problems" / name
    if not problem_dir.is_dir():
        print(f"Problem folder not found: {problem_dir}", file=sys.stderr)
        sys.exit(1)
    return problem_dir


def _problem_id(problem_dir: Path) -> str:
    meta_path = problem_dir / ".polygon.json"
    if not meta_path.exists():
        print(f"No .polygon.json in {problem_dir} — sync the problem first.", file=sys.stderr)
        sys.exit(1)
    meta = json.loads(meta_path.read_text())
    pid = meta.get("problemId")
    if not pid:
        print("problemId missing from .polygon.json", file=sys.stderr)
        sys.exit(1)
    return str(pid)


def _access_cmd(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m polyup access",
        description="List or grant Polygon problem access (problem.setAccess / problem.accesses)",
    )
    parser.add_argument("problem", help="Problem folder name under problems/")
    parser.add_argument("--list", action="store_true", help="List current direct access entries")
    parser.add_argument(
        "--access",
        nargs="*",
        metavar="USER:LEVEL",
        help="Grant access, e.g. --access alice:WRITE bob:READ (NONE revokes direct access)",
    )
    parser.add_argument("--api-delay", type=float, default=0.3)
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    _load_env(repo_root / ".env")
    problem_dir = _problem_dir(repo_root, args.problem)
    pid = _problem_id(problem_dir)
    api = _api(repo_root, args.api_delay)

    try:
        if args.list or not args.access:
            print(f"Access for problem id={pid}")
            list_accesses(api, pid)
            if not args.access:
                return 0

        access = collect_access(repo_root, problem_dir, args.access)
        grant_access(api, pid, access)
    except PolygonAPIError as exc:
        _exit_on_api_error(exc)
    return 0


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "preflight":
        from .preflight import main as preflight_main

        raise SystemExit(preflight_main(sys.argv[2:]))
    if len(sys.argv) >= 2 and sys.argv[1] == "originality":
        from .originality import main as originality_main

        raise SystemExit(originality_main(sys.argv[2:]))
    if len(sys.argv) >= 2 and sys.argv[1] == "access":
        raise SystemExit(_access_cmd(sys.argv[2:]))

    parser = argparse.ArgumentParser(
        description="Sync a problem folder to Polygon",
        epilog="Subcommands: python -m polyup originality <problem> | python -m polyup access <problem> [--list] [--access USER:LEVEL ...]",
    )
    parser.add_argument("problem", help="Problem folder name (under problems/)")
    parser.add_argument("--dry-run", action="store_true", help="Alias for read-only plan (default)")
    parser.add_argument("--apply", action="store_true", help="Explicitly allow remote writes")
    parser.add_argument("--allow-overwrite", action="store_true", help="Acknowledge modifying an existing Polygon problem")
    parser.add_argument("--expected-revision", help="Optional pinned revision; refuse changes if remote differs")
    parser.add_argument("--time-limit", type=int, default=1000, help="Time limit in ms (default: 1000)")
    parser.add_argument("--memory-limit", type=int, default=256, help="Memory limit in MB (default: 256)")
    parser.add_argument("--lang", default="english", help="Statement language (default: english)")
    parser.add_argument("--no-build", action="store_true", help="Skip package build")
    parser.add_argument("--no-verify", action="store_true", help="Build without verification")
    parser.add_argument("--commit-message", default="polyup auto-upload")
    parser.add_argument("--api-delay", type=float, default=0.3, help="Delay between API calls in seconds")
    parser.add_argument(
        "--access",
        nargs="*",
        metavar="USER:LEVEL",
        help="Grant access via problem.setAccess (e.g. --access user1:WRITE user2:READ)",
    )
    parser.add_argument("--no-access", action="store_true", help="Skip granting access")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")

    repo_root = Path(__file__).resolve().parent.parent
    _load_env(repo_root / ".env")
    problem_dir = _problem_dir(repo_root, args.problem)

    try:
        access = collect_access(repo_root, problem_dir, args.access)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    config = SyncConfig(
        time_limit_ms=args.time_limit,
        memory_limit_mb=args.memory_limit,
        statement_lang=args.lang,
        commit_message=args.commit_message,
        api_delay=args.api_delay,
        build_package=not args.no_build,
        verify_package=not args.no_verify,
        access=access,
        grant_access=not args.no_access,
    )
    # No Polygon client/credentials needed when merely planning a new problem.
    meta_file = problem_dir / ".polygon.json"
    metadata = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    existing = bool(metadata.get("problemId"))
    try:
        api = _api(repo_root, config.api_delay) if existing or args.apply else None
        plan = build_sync_plan(problem_dir, api)
        if args.expected_revision is not None and plan["remoteRevision"] != args.expected_revision:
            raise UnsafeSyncError("Remote revision differs from --expected-revision; refusing to sync")
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        if not args.apply:
            print("Read-only plan completed; no Polygon writes. Use --apply to enable writes.")
            return
        if existing and not args.allow_overwrite:
            raise UnsafeSyncError(
                "Existing Polygon problem: --apply requires --allow-overwrite "
                "and approval of the plan above"
            )
        sync_problem(problem_dir, api, config, plan=plan, allow_overwrite=args.allow_overwrite)
    except PolygonAPIError as exc:
        _exit_on_api_error(exc)


if __name__ == "__main__":
    main()
