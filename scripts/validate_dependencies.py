#!/usr/bin/env python3
"""Fail if a published POM depends on an in.payu coordinate this repo cannot serve.

Transition (default):
  Missing locally but present on Maven Central → warning
  Missing locally and not on Central → error

Strict (--strict or PAYU_MAVEN_STRICT=1), for new releases after leaving Central:
  Any missing local in.payu coordinate → error
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from lib import (
    GROUP_ID,
    GROUP_PATH,
    iter_published_poms,
    list_versions,
    local_versions_matching,
    parse_pom,
    version_in_range,
)

CENTRAL = "https://repo1.maven.org/maven2"
_central_versions: dict[str, list[str] | None] = {}


def central_versions(artifact_id: str) -> list[str] | None:
    if artifact_id in _central_versions:
        return _central_versions[artifact_id]
    url = f"{CENTRAL}/in/payu/{artifact_id}/maven-metadata.xml"
    request = urllib.request.Request(url, headers={"User-Agent": "payu-android-maven-validate/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            root = ET.fromstring(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _central_versions[artifact_id] = None
            return None
        raise
    except OSError:
        _central_versions[artifact_id] = None
        return None
    versions = [node.text.strip() for node in root.findall("versioning/versions/version") if node.text]
    _central_versions[artifact_id] = versions
    return versions


def resolve_status(artifact_id: str, spec: str) -> str:
    if local_versions_matching(artifact_id, spec):
        return "local"
    remote = central_versions(artifact_id) or []
    if any(version_in_range(version, spec) for version in remote):
        return "central"
    if list_versions(GROUP_ID, artifact_id) or remote:
        return "version-missing"
    return "missing"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        default=os.environ.get("PAYU_MAVEN_STRICT") == "1",
        help="Fail when an in.payu dependency is not in this repo (post-Central).",
    )
    parser.add_argument(
        "--all-versions",
        action="store_true",
        help="Validate every published POM. Default with --strict is latest-only.",
    )
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    pom_paths = iter_published_poms()
    if args.strict and not args.all_versions and GROUP_PATH.exists():
        latest_poms: list = []
        for artifact_path in sorted(p for p in GROUP_PATH.iterdir() if p.is_dir()):
            versions = list_versions(GROUP_ID, artifact_path.name)
            if not versions:
                continue
            latest_poms.extend(sorted((artifact_path / versions[-1]).glob("*.pom")))
        pom_paths = latest_poms

    for pom_path in pom_paths:
        pom = parse_pom(pom_path)
        source = f"{pom['groupId']}:{pom['artifactId']}:{pom['version']}"
        for dep in pom["dependencies"]:
            if dep.get("groupId") != GROUP_ID:
                continue
            spec = dep.get("version") or ""
            coordinate = f"{GROUP_ID}:{dep['artifactId']}:{spec or '?'}"
            status = resolve_status(dep["artifactId"], spec)
            if status == "local":
                continue
            message = f"{source} → {coordinate} ({status})"
            if status == "central" and not args.strict:
                warnings.append(message)
            else:
                errors.append(message)

    for warning in warnings:
        print(f"WARN  {warning}")
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)

    if errors:
        mode = "strict" if args.strict else "default"
        print(
            f"\nValidation failed ({mode}): {len(errors)} missing in.payu "
            "dependencies. Publish those artifacts here before releasing.",
            file=sys.stderr,
        )
        return 1

    print(f"OK  all in.payu dependencies resolve locally{' or on Maven Central' if not args.strict else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
