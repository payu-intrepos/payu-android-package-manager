#!/usr/bin/env python3
"""Write Maven Central-style directory index.html files under repo/.

GitHub Pages has no auto folder listing. Gradle does not need these files.
They exist so a browser opening .../payu-checkout-pro/ does not 404.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from lib import MAVEN_ROOT

SKIP_NAMES = {".nojekyll"}


def entries(directory: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for child in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.name in SKIP_NAMES or child.name.startswith("."):
            continue
        if child.name == "index.html":
            continue
        if child.is_dir():
            name = child.name + "/"
            rows.append((name, name, "-"))
        else:
            rows.append((child.name, child.name, str(child.stat().st_size)))
    return rows


def render(directory: Path, rel: str) -> str:
    title = f"PayU Maven: /{rel}" if rel else "PayU Maven Repository"
    parent_link = "" if directory == MAVEN_ROOT else '<a href="../">../</a>\n'
    lines = [
        "<!DOCTYPE html>",
        "<html lang=\"en\"><head><meta charset=\"utf-8\">",
        f"<title>{escape(title)}</title>",
        "<style>body{font-family:monospace;margin:24px} a{display:inline-block;min-width:28em}</style>",
        "</head><body>",
        f"<h1>{escape(title)}</h1><hr><pre>",
        parent_link,
    ]
    for name, href, size in entries(directory):
        lines.append(f'<a href="{escape(href)}">{escape(name)}</a> {size}')
    lines.extend(
        [
            "</pre><hr>",
            "<p>Gradle downloads maven-metadata.xml and exact AAR/POM files. It does not list directories.</p>",
            "</body></html>",
            "",
        ]
    )
    return "\n".join(lines)


def write_indexes(directory: Path) -> int:
    count = 1
    rel = directory.relative_to(MAVEN_ROOT).as_posix()
    if rel == ".":
        rel = ""
    (directory / "index.html").write_text(render(directory, rel), encoding="utf-8")
    for child in directory.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            count += write_indexes(child)
    return count


def main() -> None:
    if not MAVEN_ROOT.exists():
        raise SystemExit(f"Missing {MAVEN_ROOT}")
    n = write_indexes(MAVEN_ROOT)
    print(f"Wrote {n} index.html files under {MAVEN_ROOT}")


if __name__ == "__main__":
    main()
