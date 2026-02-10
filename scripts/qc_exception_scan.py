"""List try/except and try/catch patterns in modified Python/TypeScript files."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Final

ROOT: Final[Path] = Path(__file__).resolve().parents[1]

PY_TRY_RE: Final[re.Pattern[str]] = re.compile(r"^\s*try\s*:\s*(#.*)?$")
PY_EXCEPT_RE: Final[re.Pattern[str]] = re.compile(r"^\s*except(?:\s+[^\n:]+)?\s*:\s*(#.*)?$")
TS_TRY_RE: Final[re.Pattern[str]] = re.compile(r"\btry\b")
TS_CATCH_RE: Final[re.Pattern[str]] = re.compile(r"\bcatch\s*\(")


def run_git(args: list[str]) -> list[str]:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def collect_modified_code_files() -> list[Path]:
    files: set[str] = set()
    files.update(run_git(["diff", "--name-only"]))
    files.update(run_git(["diff", "--cached", "--name-only"]))
    files.update(run_git(["ls-files", "--others", "--exclude-standard"]))

    supported: list[Path] = []
    for rel_path in sorted(files):
        if not (rel_path.endswith(".py") or rel_path.endswith(".ts")):
            continue
        abs_path: Path = ROOT / rel_path
        if abs_path.is_file():
            supported.append(abs_path)
    return supported


def scan_python_line(line: str) -> str | None:
    if PY_TRY_RE.search(line):
        return "py_try"
    if PY_EXCEPT_RE.search(line):
        return "py_except"
    return None


def scan_typescript_line(line: str) -> str | None:
    if TS_CATCH_RE.search(line):
        return "ts_catch"
    if TS_TRY_RE.search(line):
        return "ts_try"
    return None


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    lines: list[str] = path.read_text(encoding="utf-8").splitlines()

    for lineno, line in enumerate(lines, start=1):
        kind: str | None
        if path.suffix == ".py":
            kind = scan_python_line(line)
        else:
            kind = scan_typescript_line(line)
        if kind is not None:
            findings.append((lineno, kind, line.strip()))
    return findings


def main() -> int:
    modified_files: list[Path] = collect_modified_code_files()
    print("Exception Pattern QC (modified files)")
    print("")

    if not modified_files:
        print("No modified .py/.ts files detected.")
        return 0

    total_findings: int = 0
    for file_path in modified_files:
        findings = scan_file(file_path)
        if not findings:
            continue
        total_findings += len(findings)
        rel = file_path.relative_to(ROOT)
        print(f"{rel}:")
        for lineno, kind, text in findings:
            print(f"  L{lineno} {kind}: {text}")
        print("")

    if total_findings == 0:
        print("No try/except or try/catch patterns found in modified files.")
    else:
        print(f"Total findings: {total_findings}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
