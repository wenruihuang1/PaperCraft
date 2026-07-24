#!/usr/bin/env python3
"""Check the local prerequisites required by the PaperCraft Codex plugin."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def project_root() -> Path:
    override = os.getenv("PAPERCRAFT_PROJECT_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip().splitlines()[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--auth-probe",
        action="store_true",
        help="make one minimal Codex request to verify the saved token remotely",
    )
    args = parser.parse_args()
    root = project_root()
    engine = root / "papercraft"
    cli = engine / ".venv" / "bin" / "papercraft"
    codex_home = Path(os.getenv("CODEX_HOME", Path.home() / ".codex"))
    checks = {
        "project_root": str(root),
        "engine_present": (engine / "src" / "papercraft" / "service.py").is_file(),
        "papercraft_cli": str(cli) if cli.is_file() else None,
        "python": sys.version.split()[0],
        "codex": version([shutil.which("codex") or "codex", "--version"]),
        "node": version([shutil.which("node") or "node", "--version"]),
        "npm": version([shutil.which("npm") or "npm", "--version"]),
        "saved_codex_auth_present": (codex_home / "auth.json").is_file(),
    }
    if args.auth_probe:
        with tempfile.TemporaryDirectory(prefix="papercraft-auth-probe-") as temp:
            environment = os.environ.copy()
            for name in (
                "OPENAI_API_KEY",
                "CODEX_API_KEY",
                "ANTHROPIC_API_KEY",
                "GOOGLE_API_KEY",
                "ZHIPU_API_KEY",
            ):
                environment.pop(name, None)
            try:
                probe = subprocess.run(
                    [
                        shutil.which("codex") or "codex",
                        "exec",
                        "--ephemeral",
                        "--skip-git-repo-check",
                        "--sandbox",
                        "read-only",
                        "--cd",
                        temp,
                        "Reply with exactly ok.",
                    ],
                    text=True,
                    capture_output=True,
                    timeout=180,
                    env=environment,
                )
                checks["codex_auth_probe"] = {
                    "ok": probe.returncode == 0,
                    "message": (
                        "ok"
                        if probe.returncode == 0
                        else " ".join((probe.stderr or probe.stdout).split())[-800:]
                    ),
                }
            except (OSError, subprocess.TimeoutExpired) as exc:
                checks["codex_auth_probe"] = {"ok": False, "message": str(exc)}
    checks["ready"] = bool(
        checks["engine_present"]
        and checks["papercraft_cli"]
        and checks["codex"]
        and checks["node"]
        and checks["npm"]
        and (
            not args.auth_probe
            or bool((checks.get("codex_auth_probe") or {}).get("ok"))
        )
    )
    print(json.dumps(checks, indent=2))
    return 0 if checks["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
