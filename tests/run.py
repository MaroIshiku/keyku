#!/usr/bin/env python3
"""Run Keyku's pinned test environment locally and in the managed CI workflow."""

from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "argon2-cffi": "25.1.0",
    "Flask": "3.1.3",
    "gunicorn": "26.2.0",
    "pytest": "9.1.1",
}


def dependencies_are_current() -> bool:
    try:
        return all(importlib.metadata.version(name) == version for name, version in REQUIRED.items())
    except importlib.metadata.PackageNotFoundError:
        return False


def run_tests(python: Path) -> int:
    return subprocess.run(
        [str(python), "-m", "pytest", "-q"],
        cwd=ROOT,
        check=False,
    ).returncode


def main() -> int:
    if dependencies_are_current():
        return run_tests(Path(sys.executable))

    environment = Path(tempfile.mkdtemp(prefix="keyku-test-venv-"))
    try:
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = environment / "bin" / "python"
        installed = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--requirement",
                str(ROOT / "python" / "requirements-dev.txt"),
            ],
            cwd=ROOT,
            check=False,
        )
        return installed.returncode or run_tests(python)
    finally:
        shutil.rmtree(environment, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
