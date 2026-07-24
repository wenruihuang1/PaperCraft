#!/usr/bin/env python3
"""Run one or more PDFs through PaperCraft's Codex-only pipeline."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def project_root() -> Path:
    override = os.getenv("PAPERCRAFT_PROJECT_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path, nargs="+")
    args = parser.parse_args()
    root = project_root()
    engine = root / "papercraft"
    executable = engine / ".venv" / "bin" / "papercraft"
    if not executable.is_file():
        parser.error(
            f"PaperCraft CLI not found at {executable}; install the engine first"
        )
    environment = os.environ.copy()
    for name in (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "ZHIPU_API_KEY",
    ):
        environment.pop(name, None)
    for supplied in args.pdf:
        pdf = supplied.expanduser().resolve()
        if not pdf.is_file():
            parser.error(f"PDF not found: {pdf}")
        completed = subprocess.run(
            [str(executable), "codex-run", str(pdf)],
            cwd=engine,
            env=environment,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
