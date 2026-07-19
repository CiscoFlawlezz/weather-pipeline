#!/usr/bin/env bash
# Regenerate Repository_Manifest.txt from tracked files.
# Mirrors the vault repo's generator so both repos stay drift-free.
# The manifest lists only git-tracked files, so gitignored scratch
# (samples_kalshi/, data/, *.db) never appears -- the manifest reflects
# exactly what is in version control, nothing more.
set -euo pipefail
cd "$(dirname "$0")"
git -c core.quotepath=false ls-files \
  > Repository_Manifest.txt
echo "Manifest regenerated: $(wc -l < Repository_Manifest.txt) entries"