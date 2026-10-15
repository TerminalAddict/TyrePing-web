#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$repo_root/scripts/check.py"

# Preserve the current site outside the public directory before replacing files.
ssh -o BatchMode=yes -o ConnectTimeout=10 paul@webhost2 'bash -s' <<'REMOTE'
set -euo pipefail
backup_dir="$HOME/site-backups/tyreping.com"
mkdir -p "$backup_dir"
backup_file="$backup_dir/$(date -u +%Y%m%dT%H%M%S)-$$.tar.gz"
tar -czf "$backup_file" -C /var/www/html/tyreping.com .
printf 'Previous site backed up to %s\n' "$backup_file"
REMOTE

rsync -rz --checksum --perms --chmod=D755,F644 --omit-dir-times --itemize-changes \
  -e 'ssh -o BatchMode=yes -o ConnectTimeout=10' \
  "$repo_root/public/" paul@webhost2:/var/www/html/tyreping.com/

for route in / /install/ /privacy/ /licenses/ /licenses/Apache-2.0.txt /licenses/ATTRIBUTIONS.txt /robots.txt /sitemap.xml /site.webmanifest /favicon.ico; do
  curl --fail --silent --show-error --max-time 20 --output /dev/null "https://www.tyreping.com$route"
done
printf 'Deployed and reachable: https://www.tyreping.com\n'
