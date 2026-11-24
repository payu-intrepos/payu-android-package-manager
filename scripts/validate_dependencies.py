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
import time
import urllib.error
import urllib.parse
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
PAYU_REMOTE = "https://payu-intrepos.github.io/payu-android-package-manager"

# Codes worth retrying: the host is up but cannot answer right now.
TRANSIENT_CODES = {408, 425, 429, 500, 502, 503, 504}
RETRIES = 3

_versions_cache: dict[str, list[str] | None] = {}
unreachable: set[str] = set()


def fetch_versions(url: str) -> list[str] | None:
    """Versions listed in a maven-metadata.xml, or None if absent or unreachable.

    A 404 means the artifact genuinely is not there. Anything else is a failure to
    answer, not an answer: retry, and if it keeps failing record the host in
    `unreachable` so the summary can say the check was skipped rather than let a
    transient outage read as a missing dependency.
    """
    if url in _versions_cache:
        return _versions_cache[url]

    request = urllib.request.Request(url, headers={"User-Agent": "payu-android-maven-validate/1.0"})
    host = urllib.parse.urlsplit(url).netloc
    versions: list[str] | None = None

    for attempt in range(RETRIES):
        last = attempt == RETRIES - 1
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                root = ET.fromstring(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                break
            if exc.code in TRANSIENT_CODES and not last:
                time.sleep(2**attempt)
                continue
            unreachable.add(f"{host} (HTTP {exc.code})")
            break
        except (OSError, ET.ParseError) as exc:
            if not last:
                time.sleep(2**attempt)
                continue
            unreachable.add(f"{host} ({exc})")
            break
        found = [node.text.strip() for node in root.findall("versioning/versions/version") if node.text]
        versions = found or None
        break

    _versions_cache[url] = versions
    return versions


def central_versions(artifact_id: str) -> list[str] | None:
    return fetch_versions(f"{CENTRAL}/in/payu/{artifact_id}/maven-metadata.xml")


def payu_remote_versions(artifact_id: str) -> list[str] | None:
    """Check PayU remote Maven repository (GitHub Pages)."""
    # The Pages site serves the contents of repo/ at its root, so no /repo/ prefix.
    return fetch_versions(f"{PAYU_REMOTE}/in/payu/{artifact_id}/maven-metadata.xml")


def resolve_status(artifact_id: str, spec: str) -> str:
    # Priority order: Maven Central → PayU Remote → PayU Local

    # 1. Check Maven Central first
    central = central_versions(artifact_id) or []
    if any(version_in_range(version, spec) for version in central):
        return "central"

    # 2. Check PayU remote repository
    payu_remote = payu_remote_versions(artifact_id) or []
    if any(version_in_range(version, spec) for version in payu_remote):
        return "payu-remote"

    # 3. Check local PayU Maven repo
    if local_versions_matching(artifact_id, spec):
        return "local"

    # If version exists anywhere but not matching spec
    if central or payu_remote or list_versions(GROUP_ID, artifact_id):
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
    parser.add_argument(
        "--artifact-id",
        help="Validate only this artifact ID (skips other POMs in repo).",
    )
    parser.add_argument(
        "--artifact-version",
        help="Validate only this artifact version (used with --artifact-id).",
    )
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    # If specific artifact is provided, validate only that POM
    if args.artifact_id and args.artifact_version:
        from pathlib import Path
        artifact_dir = Path(GROUP_PATH) / args.artifact_id / args.artifact_version
        if artifact_dir.exists():
            pom_paths = sorted(artifact_dir.glob("*.pom"))
        else:
            pom_paths = []
    else:
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

            # Status hierarchy: local ✓, central ✓, payu-remote ✓, version-missing ✗, missing ✗
            if status in ("local", "central", "payu-remote"):
                # Dependency found - only warn in non-strict mode if from central
                if status == "central" and not args.strict:
                    message = f"{source} → {coordinate} ({status})"
                    warnings.append(message)
                continue

            # Dependency not found or version missing
            message = f"{source} → {coordinate} ({status})"
            errors.append(message)

    for host in sorted(unreachable):
        print(f"WARN  could not reach {host}; its versions were not considered")
    for warning in warnings:
        print(f"WARN  {warning}")
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)

    if errors:
        mode = "strict" if args.strict else "default"
        print(
            f"\nValidation failed ({mode}): {len(errors)} missing in.payu "
            "dependencies. Publish those artifacts here before releasing."
            + (
                f"\nNote: {', '.join(sorted(unreachable))} could not be reached, "
                "so some of these may exist there."
                if unreachable
                else ""
            ),
            file=sys.stderr,
        )
        return 1

    sources = "locally, from PayU Remote, or from Maven Central" if not args.strict else "locally"
    print(f"OK  all in.payu dependencies resolve {sources}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
