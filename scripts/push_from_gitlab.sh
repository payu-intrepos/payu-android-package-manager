#!/usr/bin/env bash
# Publish a Gradle maven repo directory into this GitHub Pages repository.
#
# Required CI variables:
#   GITHUB_MAVEN_TOKEN   PAT with contents:write on payu-intrepos/payu-android-maven
#   GITHUB_MAVEN_REPO    defaults to payu-intrepos/payu-android-maven
#   GRADLE_MAVEN_DIR     defaults to build/payu-maven
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GITHUB_MAVEN_REPO="${GITHUB_MAVEN_REPO:-payu-intrepos/payu-android-maven}"
GRADLE_MAVEN_DIR="${GRADLE_MAVEN_DIR:-${ROOT_DIR}/../build/payu-maven}"
WORK_DIR="${TMPDIR:-/tmp}/payu-android-maven-publish"

if [[ -z "${GITHUB_MAVEN_TOKEN:-}" ]]; then
  echo "GITHUB_MAVEN_TOKEN is required" >&2
  exit 1
fi

if [[ ! -d "${GRADLE_MAVEN_DIR}" ]]; then
  echo "Gradle Maven output not found: ${GRADLE_MAVEN_DIR}" >&2
  echo "Run: ./gradlew publishAllPublicationsToPayuLocalRepository" >&2
  exit 1
fi

rm -rf "${WORK_DIR}"
git clone --depth 1 "https://x-access-token:${GITHUB_MAVEN_TOKEN}@github.com/${GITHUB_MAVEN_REPO}.git" "${WORK_DIR}"

PAYU_MAVEN_STRICT="${PAYU_MAVEN_STRICT:-1}" "${WORK_DIR}/scripts/publish.sh" "${GRADLE_MAVEN_DIR}"

cd "${WORK_DIR}"
git add repo
if git diff --cached --quiet; then
  echo "No new Maven artifacts to publish"
  exit 0
fi

git config user.name "${GITLAB_USER_NAME:-PayU SDK CI}"
git config user.email "${GITLAB_USER_EMAIL:-sdk-ci@payu.in}"
git commit -m "Publish SDK artifacts from GitLab ${CI_COMMIT_SHA:-local}"
git push origin HEAD:main
echo "Published to https://payu-intrepos.github.io/payu-android-maven/"
