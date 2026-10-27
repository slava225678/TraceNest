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


def check_line_lengths() -> None:
    suffixes = {".py", ".html", ".css", ".js", ".toml", ".yml", ".mako"}
    root_names = {
        "Dockerfile",
        "Dockerfile.test",
        "LICENSE",
        ".env.example",
        ".editorconfig",
        ".gitattributes",
        ".gitignore",
        ".dockerignore",
        ".gitignore",
    }
    root_suffixes = suffixes | {".md", ".txt", ".ini"}
    files = [
        file
        for file in ROOT.iterdir()
        if file.is_file()
        and (file.suffix in root_suffixes or file.name in root_names)
    ]
    files.extend(file for file in (ROOT / "sdk").iterdir() if file.is_file())
    for directory in SOURCE_DIRS:
        files.extend(
            file
            for file in (ROOT / directory).rglob("*")
            if file.is_file() and file.suffix in suffixes
        )
    failures = []
    for file in files:
        for number, line in enumerate(
            file.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if len(line) > 79:
                failures.append(f"{file.relative_to(ROOT)}:{number}")
    if failures:
        raise SystemExit("Lines over 79 characters:\n" + "\n".join(failures))
    print("Strict 79-character limit: passed", flush=True)


def run(*args: str) -> None:
    print("Running: python " + " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main() -> None:
    run("-m", "ruff", "check", ".")
    run("-m", "ruff", "format", "--check", ".")
    check_line_lengths()
    run("-m", "pytest", "-q", "-p", "no:cacheprovider")
    run("-m", "build", "--no-isolation", "--outdir", "dist/sdk", "sdk")


if __name__ == "__main__":
    main()
