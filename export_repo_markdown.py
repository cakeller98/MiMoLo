#!/usr/bin/env python
"""
Export repository files into a single Markdown document.

Each included file becomes:

## <relative_or_absolute_path>

``` <extension>
<file contents>
```

The script excludes certain directories and only includes
files with specific extensions.

The script will create a single monolithic file to share
with an AI system for code review or analysis without
having to explain the repository structure.

for relative paths, run:
poetry run python export_repo_markdown.py --output repo_export.md

for absolute paths, run:
poetry run python export_repo_markdown.py --absolute --output repo_export.md

"""

from __future__ import annotations

from pathlib import Path

import typer

INCLUDE_EXTS = {
    ".py",
    ".toml",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".sh",
    ".ps1",
    ".bat",
    ".ini",
    ".cfg",
    ".csv",
}
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "logs",
    ".mypy_cache",
    ".ruff_cache",
}


def should_include(path: Path, output_file: Path) -> bool:
    if path.is_dir():
        return False
    if path.resolve() == output_file.resolve():
        return False  # ✅ prevent self-inclusion
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return False
    return path.suffix.lower() in INCLUDE_EXTS


def export_repo_markdown(
    root: Path, output_file: Path, relative: bool = True
) -> None:
    files = sorted(
        root.rglob("*"),
        key=lambda p: (str(p.parent).lower(), p.name.lower()),
    )
    with output_file.open("w", encoding="utf-8") as out:
        for file_path in files:
            if not should_include(file_path, output_file):
                continue
            heading = (
                file_path.relative_to(root)
                if relative
                else file_path.resolve()
            )
            ext = file_path.suffix.lstrip(".").lower() or "text"
            if ext == "yml":
                ext = "yaml"
            out.write(f"## {heading}\n\n")
            out.write(f"``` {ext}\n")
            try:
                contents = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
            except Exception as e:
                contents = f"[Error reading file: {e}]"
            out.write(contents.rstrip() + "\n```\n\n")
    print(f"✅ Export complete → {output_file}")


app = typer.Typer()


@app.command()
def main(
    root: Path = typer.Option(
        Path.cwd(),
        help="Root directory to export.",
    ),
    output: Path = typer.Option(
        Path("repo_export.md"),
        help="Output Markdown file.",
    ),
    absolute: bool = typer.Option(
        False,
        help="Use absolute paths in headings instead of relative.",
    ),
) -> None:
    """Export repository files to a single Markdown document."""
    export_repo_markdown(root, output, relative=not absolute)


if __name__ == "__main__":
    app()
