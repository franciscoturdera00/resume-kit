#!/usr/bin/env bash
# Package resume-kit.skill from TRACKED files only (git archive), so user data
# living in this working tree (master_resume.json, deliverables/, ...) can never
# end up in the package. Run from anywhere inside the repo.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
mkdir -p dist
git archive --format=zip --prefix=resume-kit/ -o dist/resume-kit.skill HEAD \
  ":!.github" ":!scripts/package.sh" ":!tests"
echo "Wrote dist/resume-kit.skill from commit $(git rev-parse --short HEAD):"
unzip -l dist/resume-kit.skill | tail -3
