#!/usr/bin/env bash
# Internal helper: upload verified assets before the page that links to them.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$repo_root/public/downloads/index.html"
test -f "$repo_root/public/downloads/releases.json"
ssh -o BatchMode=yes -o ConnectTimeout=10 paul@webhost2 \
  'mkdir -p /var/www/html/tyreping.com/downloads/files'

rsync -rz --checksum --perms --chmod=D755,F644 --omit-dir-times \
  -e 'ssh -o BatchMode=yes -o ConnectTimeout=10' \
  "$repo_root/public/downloads/files/" paul@webhost2:/var/www/html/tyreping.com/downloads/files/
rsync -rz --checksum --perms --chmod=D755,F644 --omit-dir-times \
  --exclude 'files/' --exclude 'index.html' \
  -e 'ssh -o BatchMode=yes -o ConnectTimeout=10' \
  "$repo_root/public/downloads/" paul@webhost2:/var/www/html/tyreping.com/downloads/
rsync -rz --checksum --perms --chmod=F644 --omit-dir-times \
  -e 'ssh -o BatchMode=yes -o ConnectTimeout=10' \
  "$repo_root/public/downloads/index.html" paul@webhost2:/var/www/html/tyreping.com/downloads/index.html

# Only the generated binary directory is pruned. This also removes hosted APKs
# when play-store mode builds an empty files/ directory.
rsync -rz --checksum --perms --chmod=D755,F644 --omit-dir-times --delete \
  -e 'ssh -o BatchMode=yes -o ConnectTimeout=10' \
  "$repo_root/public/downloads/files/" paul@webhost2:/var/www/html/tyreping.com/downloads/files/

curl --fail --silent --show-error --max-time 20 --output /dev/null https://www.tyreping.com/downloads/
curl --fail --silent --show-error --max-time 20 --output /dev/null https://www.tyreping.com/downloads/releases.json
