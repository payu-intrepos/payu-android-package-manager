#!/usr/bin/env python3
"""Copy a built AAR/JAR/POM into the static Maven layout.

Example:
  python3 scripts/publish_artifact.py \\
    --group in.payu \\
    --artifact payu-checkout-pro \\
    --version 3.3.16 \\
    --file path/to/payu-checkout-pro-3.3.16.aar \\
    --file path/to/payu-checkout-pro-3.3.16.pom
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from lib import (
    GROUP_ID,
    MAVEN_ROOT,
    refresh_all_metadata,
    version_dir,
    write_checksums,
    write_maven_metadata,
)


def publish_files(group_id: str, artifact_id: str, version: str, files: list[Path], overwrite: bool) -> None:
    dest_dir = version_dir(group_id, artifact_id, version)
    if dest_dir.exists() and any(dest_dir.iterdir()) and not overwrite:
        raise SystemExit(
            f"{group_id}:{artifact_id}:{version} already exists. "
            "Release versions are immutable. Use --overwrite only to fix a broken publish."
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in files:
        if not src.is_file():
            raise SystemExit(f"File not found: {src}")
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        write_checksums(dest)
        print(f"published {dest.relative_to(MAVEN_ROOT)}")

    write_maven_metadata(group_id, artifact_id)


def import_gradle_repo(source: Path, overwrite: bool) -> int:
    """Import a Gradle maven { url = build/payu-maven } directory."""
    if not source.is_dir():
        raise SystemExit(f"Gradle Maven repo not found: {source}")

    count = 0
    for pom in source.rglob("*.pom"):
        rel = pom.relative_to(source)
        parts = rel.parts
        if len(parts) < 3:
            continue
        version = parts[-2]
        artifact_id = parts[-3]
        group_id = ".".join(parts[:-3])
        dest_dir = version_dir(group_id, artifact_id, version)
        if dest_dir.exists() and any(dest_dir.iterdir()) and not overwrite:
            print(f"skip  {group_id}:{artifact_id}:{version}")
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        for src in pom.parent.iterdir():
            if src.is_file() and not src.name.endswith((".md5", ".sha1", ".sha256", ".sha512")):
                shutil.copy2(src, dest_dir / src.name)
                write_checksums(dest_dir / src.name)
                count += 1
        write_maven_metadata(group_id, artifact_id)
        print(f"imported {group_id}:{artifact_id}:{version}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default=GROUP_ID)
    parser.add_argument("--artifact")
    parser.add_argument("--version")
    parser.add_argument("--file", action="append", dest="files", type=Path)
    parser.add_argument(
        "--from-gradle-repo",
        type=Path,
        help="Import every artifact from a Gradle maven repository directory.",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.from_gradle_repo:
        imported = import_gradle_repo(args.from_gradle_repo, args.overwrite)
        refresh_all_metadata()
        print(f"Imported {imported} files")
        return 0

    if not (args.artifact and args.version and args.files):
        parser.error("Provide --artifact, --version and --file, or --from-gradle-repo")

    publish_files(args.group, args.artifact, args.version, args.files, args.overwrite)
    return 0


if __name__ == "__main__":
    sys.exit(main())
