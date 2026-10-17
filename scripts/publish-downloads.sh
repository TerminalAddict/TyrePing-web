#!/usr/bin/env bash
# Refresh both app channels without republishing the rest of the website.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec 9>"$repo_root/.publish-downloads.lock"
flock -n 9 || { printf 'Another download publication is running.\n' >&2; exit 1; }
python3 "$repo_root/scripts/sync_releases.py"
python3 "$repo_root/scripts/check.py"
ssh -o BatchMode=yes -o ConnectTimeout=10 paul@webhost2 'bash -s' <<'REMOTE'
set -euo pipefail
backup_dir="$HOME/site-backups/tyreping.com"
mkdir -p "$backup_dir" /var/www/html/tyreping.com/downloads/files
backup_file="$backup_dir/downloads-$(date -u +%Y%m%dT%H%M%S)-$$.tar.gz"
tar -czf "$backup_file" -C /var/www/html/tyreping.com downloads
printf 'Downloads backed up to %s\n' "$backup_file"
REMOTE
bash "$repo_root/scripts/upload-downloads.sh"
printf 'Published app downloads: https://www.tyreping.com/downloads/\n'
