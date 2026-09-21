#!/usr/bin/env python3
"""Shared helpers for the PayU static Maven repository."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAVEN_ROOT = REPO_ROOT / "repo"
GROUP_ID = "in.payu"
GROUP_PATH = MAVEN_ROOT / "in" / "payu"

HASH_ALGOS = ("md5", "sha1", "sha256", "sha512")
ARTIFACT_SUFFIXES = (
    ".aar",
    ".jar",
    ".pom",
    ".module",
    "-sources.jar",
    "-javadoc.jar",
)


def utc_maven_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def group_to_path(group_id: str) -> Path:
    return MAVEN_ROOT.joinpath(*group_id.split("."))


def artifact_dir(group_id: str, artifact_id: str) -> Path:
    return group_to_path(group_id) / artifact_id


def version_dir(group_id: str, artifact_id: str, version: str) -> Path:
    return artifact_dir(group_id, artifact_id) / version


def version_key(version: str) -> tuple:
    """Sort Maven-ish versions so 2.10.0 comes after 2.9.0."""
    main, sep, qualifier = version.partition("-")
    parts: list[tuple[int, str]] = []
    for token in re.split(r"[.]", main):
        if token.isdigit():
            parts.append((0, f"{int(token):08d}"))
        else:
            parts.append((1, token))
    return (parts, 1 if sep else 0, qualifier.lower())


def write_checksums(path: Path) -> None:
    data = path.read_bytes()
    for algo in HASH_ALGOS:
        digest = hashlib.new(algo, data).hexdigest()
        path.with_suffix(path.suffix + f".{algo}").write_text(digest + "\n", encoding="ascii")


def list_versions(group_id: str, artifact_id: str) -> list[str]:
    base = artifact_dir(group_id, artifact_id)
    if not base.exists():
        return []
    versions = [
        child.name
        for child in base.iterdir()
        if child.is_dir() and not child.name.startswith(".")
    ]
    return sorted(versions, key=version_key)


def write_maven_metadata(group_id: str, artifact_id: str) -> Path:
    versions = list_versions(group_id, artifact_id)
    if not versions:
        raise FileNotFoundError(f"No versions published for {group_id}:{artifact_id}")

    release_versions = [v for v in versions if "snapshot" not in v.lower()]
    latest = versions[-1]
    release = release_versions[-1] if release_versions else latest

    metadata = ET.Element("metadata")
    ET.SubElement(metadata, "groupId").text = group_id
    ET.SubElement(metadata, "artifactId").text = artifact_id
    versioning = ET.SubElement(metadata, "versioning")
    ET.SubElement(versioning, "latest").text = latest
    ET.SubElement(versioning, "release").text = release
    versions_el = ET.SubElement(versioning, "versions")
    for version in versions:
        ET.SubElement(versions_el, "version").text = version
    ET.SubElement(versioning, "lastUpdated").text = utc_maven_timestamp()

    tree = ET.ElementTree(metadata)
    ET.indent(tree, space="  ")
    dest = artifact_dir(group_id, artifact_id) / "maven-metadata.xml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tree.write(dest, encoding="utf-8", xml_declaration=True)
    write_checksums(dest)
    return dest


def refresh_all_metadata() -> list[Path]:
    written: list[Path] = []
    if not GROUP_PATH.exists():
        return written
    for artifact_path in sorted(p for p in GROUP_PATH.iterdir() if p.is_dir()):
        written.append(write_maven_metadata(GROUP_ID, artifact_path.name))
    return written


def local_name(tag: str) -> str:
    return tag.split("}")[-1]


def parse_pom(path: Path) -> dict:
    """Read groupId, artifactId, version, and dependencies from a POM."""
    root = ET.parse(path).getroot()
    fields: dict[str, str] = {}
    dependencies: list[dict[str, str]] = []

    for child in list(root):
        name = local_name(child.tag)
        if name in {"groupId", "artifactId", "version", "packaging", "name", "description"}:
            fields[name] = (child.text or "").strip()
        if name != "dependencies":
            continue
        for dep in child:
            if local_name(dep.tag) != "dependency":
                continue
            item = {
                local_name(node.tag): (node.text or "").strip()
                for node in list(dep)
                if local_name(node.tag) in {"groupId", "artifactId", "version", "scope"}
            }
            if item.get("groupId") and item.get("artifactId"):
                dependencies.append(item)

    return {
        "groupId": fields.get("groupId", GROUP_ID),
        "artifactId": fields.get("artifactId", ""),
        "version": fields.get("version", ""),
        "packaging": fields.get("packaging", "aar"),
        "name": fields.get("name", ""),
        "description": fields.get("description", ""),
        "dependencies": dependencies,
        "path": str(path),
    }


def iter_published_poms() -> list[Path]:
    if not GROUP_PATH.exists():
        return []
    return sorted(
        path
        for path in GROUP_PATH.rglob("*.pom")
        if path.is_file() and not any(part.startswith(".") for part in path.parts)
    )


def published_coordinates() -> set[tuple[str, str, str]]:
    coords: set[tuple[str, str, str]] = set()
    if not GROUP_PATH.exists():
        return coords
    for artifact_path in GROUP_PATH.iterdir():
        if not artifact_path.is_dir():
            continue
        for version in list_versions(GROUP_ID, artifact_path.name):
            coords.add((GROUP_ID, artifact_path.name, version))
    return coords


def version_in_range(version: str, spec: str) -> bool:
    """Match an exact version or a simple Maven range like [1.1.1,1.2.0)."""
    spec = spec.strip()
    if not spec:
        return False
    if spec[0] not in "[(":
        return version == spec

    if spec[-1] not in "])":
        return False
    inner = spec[1:-1]
    lower_s, _, upper_s = inner.partition(",")
    lower_s, upper_s = lower_s.strip(), upper_s.strip()
    include_lower = spec[0] == "["
    include_upper = spec[-1] == "]"

    def cmp(a: str, b: str) -> int:
        ka, kb = version_key(a), version_key(b)
        return (ka > kb) - (ka < kb)

    if lower_s:
        relation = cmp(version, lower_s)
        if relation < 0 or (relation == 0 and not include_lower):
            return False
    if upper_s:
        relation = cmp(version, upper_s)
        if relation > 0 or (relation == 0 and not include_upper):
            return False
    return True


def local_versions_matching(artifact_id: str, spec: str) -> list[str]:
    return [version for version in list_versions(GROUP_ID, artifact_id) if version_in_range(version, spec)]


def scan_artifacts() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not GROUP_PATH.exists():
        return rows
    for artifact_path in sorted(p for p in GROUP_PATH.iterdir() if p.is_dir()):
        versions = list_versions(GROUP_ID, artifact_path.name)
        if not versions:
            continue
        latest = versions[-1]
        latest_dir = artifact_path / latest
        packaging = "aar"
        if not any(latest_dir.glob("*.aar")):
            packaging = "jar" if any(latest_dir.glob("*.jar")) else "pom"
        rows.append(
            {
                "groupId": GROUP_ID,
                "artifactId": artifact_path.name,
                "latest": latest,
                "versions": str(len(versions)),
                "packaging": packaging,
                "coordinate": f"{GROUP_ID}:{artifact_path.name}:{latest}",
            }
        )
    return rows
