"""Conservative Docker-only C++17 compile/execute backend for SOL-001.

Untrusted source is never compiled/run on the host. A Docker daemon is a
privileged system component; do not treat this as a hardened hostile-code
sandbox. Use only on a machine configured for untrusted CP code, with no
sensitive directories or Docker socket mounted inside the container.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .solution_check import Execution
from .spec import ProblemSpecError

MAX_PROGRAM_BYTES = 1024 * 1024
OUTPUT_LIMIT_BYTES = 2 * 1024 * 1024
BUILD_LOG_LIMIT_BYTES = 12 * 1024
COMPILE_WALL_SECONDS = 45
RUN_WALL_SLACK_SECONDS = 3

class DockerRunner:
    """Use as a context manager; only scoped temp bind mounts are writable."""

    def __init__(self, image: str = "gcc:14"):
        if not re.fullmatch(r"[a-zA-Z0-9_./:@-]+", image):
            raise ProblemSpecError("Invalid Docker image name")
        self.image = image
        self._temp = None
        self.root = None

    def __enter__(self):
        if shutil.which("docker") is None:
            raise ProblemSpecError("Docker is required for code execution; no host fallback")
        # Do NOT pull implicitly: offline/provenance and explicit user consent.
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", self.image],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise ProblemSpecError("Cannot inspect Docker image/daemon") from None
        if result.returncode != 0:
            raise ProblemSpecError(
                f"Docker image {self.image} is unavailable locally; pull it manually after review"
            )
        self._temp = tempfile.TemporaryDirectory(prefix="factory-sol-")
        self.root = Path(self._temp.name)
        return self

    def __exit__(self, *args):
        if self._temp is not None:
            self._temp.cleanup()
            self._temp = None
            self.root = None

    def _docker(self, role: str, mounts: list[tuple[Path, str, bool]],
                script: str, wall_seconds: float, *, memory: str):
        if self.root is None:
            raise ProblemSpecError("DockerRunner must be used inside a with block")
        cidfile = self.root / f"{role}-docker.cid"
        if cidfile.exists():
            cidfile.unlink()
        uid = os.getuid() if hasattr(os, "getuid") else 1000
        gid = os.getgid() if hasattr(os, "getgid") else 1000
        if uid == 0:  # never execute the guest process as container root
            uid, gid = 65534, 65534
        cmd = [
            "docker", "run", "--rm", "--pull=never",
            "--cidfile", str(cidfile), "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--cpus", "1", "--memory", memory,
            "--memory-swap", memory, "--user", f"{uid}:{gid}",
            "--ulimit", "fsize=8388608:8388608", "--ulimit", "nofile=64:64",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m,mode=1777",
        ]
        for path, dest, readonly in mounts:
            path = path.resolve(strict=True)
            spec = f"type=bind,source={path},destination={dest}"
            if readonly:
                spec += ",readonly"
            cmd.extend(["--mount", spec])
        cmd.extend([self.image, "/bin/sh", "-c", script])
        try:
            # Program stdout and stderr are redirected to size-restricted
            # files *inside* the container, not unbounded host pipes.
            return subprocess.run(
                cmd, stdin=subprocess.DEVNULL, capture_output=True,
                timeout=wall_seconds, check=False,
            ).returncode
        except subprocess.TimeoutExpired:
            # Killing the CLI alone may leave a Docker container running.
            # Remove the exact container created for this run, if known.
            if cidfile.exists():
                cid = cidfile.read_text().strip()
                if re.fullmatch(r"[a-f0-9]{64}", cid):
                    try:
                        subprocess.run(
                            ["docker", "kill", cid],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=5, check=False,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        pass
            return -1
        except OSError:
            raise ProblemSpecError("Docker CLI failed before returning a result") from None

    def build(self, source: Path, role: str) -> Execution:
        if role not in {"candidate", "oracle"}:
            raise ProblemSpecError("Unknown build role")
        raw = Path(source).read_bytes()
        if not raw or len(raw) > MAX_PROGRAM_BYTES:
            raise ProblemSpecError("Source file must be 1 byte to 1 MiB")
        root = self.root
        if root is None:
            raise ProblemSpecError("DockerRunner must be used inside a with block")
        src = root / role / "src"
        output = root / role / "build"
        src.mkdir(parents=True)
        output.mkdir()
        src.chmod(0o755)
        output.chmod(0o777)  # only an isolated temporary output directory
        (src / "main.cpp").write_bytes(raw)
        (src / "main.cpp").chmod(0o644)
        script = ("ulimit -f 4096; "
                  "g++ -std=c++17 -O2 -pipe -o /out/program /src/main.cpp "
                  "> /out/build.log 2>&1")
        status = self._docker(
            f"build-{role}",
            [(src, "/src", True), (output, "/out", False)],
            script, COMPILE_WALL_SECONDS, memory="1g"
        )
        log = output / "build.log"
        detail = log.read_bytes()[:BUILD_LOG_LIMIT_BYTES].decode("utf-8", "replace") if log.is_file() else ""
        if status == -1:
            return Execution("COMPILE_TIMEOUT", detail="Compiler exceeded wall-time budget")
        if status != 0 or not (output / "program").is_file():
            return Execution("COMPILE_ERROR", detail=detail or "Compiler failed; inspect Docker environment")
        return Execution("OK")

    def run(self, role: str, data: bytes, timeout_s: float) -> Execution:
        if role not in {"candidate", "oracle"}:
            raise ProblemSpecError("Unknown run role")
        root = self.root
        if root is None:
            raise ProblemSpecError("DockerRunner must be used inside a with block")
        input_dir = root / f"{role}-stdin"
        output_dir = root / f"{role}-stdout"
        input_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)
        input_dir.chmod(0o755)
        output_dir.chmod(0o777)
        (input_dir / "case.in").write_bytes(data)
        (input_dir / "case.in").chmod(0o644)
        build_dir = root / role / "build"
        if not (build_dir / "program").is_file():
            raise ProblemSpecError("No compiled executable for " + role)
        for name in ("stdout", "stderr"):
            p = output_dir / name
            if p.exists():
                p.unlink()
        script = ("ulimit -f 4096; "
                  "exec /work/program < /input/case.in "
                  "> /output/stdout 2> /output/stderr")
        status = self._docker(
            f"run-{role}", [(build_dir, "/work", True),
                            (input_dir, "/input", True),
                            (output_dir, "/output", False)],
            script, timeout_s + RUN_WALL_SLACK_SECONDS, memory="256m"
        )
        if status == -1:
            return Execution("TLE", detail="Execution exceeded wall-time budget")
        stdout = output_dir / "stdout"
        stderr = output_dir / "stderr"
        size = stdout.stat().st_size if stdout.is_file() else 0
        if size >= OUTPUT_LIMIT_BYTES or status in {153, 128 + 25}:
            return Execution("OLE", detail="Execution exceeded output file limit")
        if status == 137:
            return Execution("MLE", detail="Container killed (possible memory limit)")
        if status != 0:
            err = stderr.read_bytes()[:512].decode("utf-8", "replace") if stderr.is_file() else ""
            return Execution("RE", detail=f"Process exit={status}. {err}")
        if not stdout.is_file():
            return Execution("RE", detail="Execution produced no stdout file")
        return Execution("OK", output=stdout.read_bytes())
