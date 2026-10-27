"""Run the same checks locally and in the GitHub Actions test container."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = (
    "app",
    "examples",
    "migrations",
    "scripts",
    "tests",
    ".github",
    "sdk/src/tracenest_sdk",
)


def run(*args: str) -> None:
    print("Running: python " + " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main() -> None:
    run("-m", "ruff", "check", ".")
    run("-m", "pytest", "-q", "-p", "no:cacheprovider")
    run("-m", "build", "--no-isolation", "--outdir", "dist/sdk", "sdk")


if __name__ == "__main__":
    main()
