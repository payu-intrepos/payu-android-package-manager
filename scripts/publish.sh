#!/usr/bin/env bash
# Import optional Gradle output, then refresh metadata, graph, and validation.
#
# Usage:
#   scripts/publish.sh
#   scripts/publish.sh /path/to/build/payu-maven
#
# PAYU_MAVEN_STRICT=1 (default) fails if any in.payu transitive is not in this repo.
# PAYU_MAVEN_STRICT=0 allows Maven Central fallback during the migration window.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
export PYTHONPATH="${ROOT_DIR}/scripts${PYTHONPATH:+:$PYTHONPATH}"

GRADLE_MAVEN_DIR="${1:-}"
PAYU_MAVEN_STRICT="${PAYU_MAVEN_STRICT:-1}"

if [[ -n "${GRADLE_MAVEN_DIR}" ]]; then
  python3 scripts/publish_artifact.py --from-gradle-repo "${GRADLE_MAVEN_DIR}"
fi

python3 scripts/generate_dependency_graph.py

if [[ "${PAYU_MAVEN_STRICT}" == "1" ]]; then
  python3 scripts/validate_dependencies.py --strict
else
  python3 scripts/validate_dependencies.py
fi

echo "Publish pipeline finished"
