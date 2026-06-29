#!/usr/bin/env bash
set -euo pipefail

failures=0

allow_file() {
  case "$1" in
    scripts/privacy_check.sh) return 1 ;;
    SECURITY.md) return 1 ;;
    .gitignore) return 1 ;;
    *) return 0 ;;
  esac
}

check_pattern() {
  local file="$1"
  local rule="$2"
  local pattern="$3"
  if grep -InE "$pattern" "$file" >/tmp/jarvis_privacy_matches.txt 2>/dev/null; then
    while IFS= read -r line; do
      printf 'PRIVACY CHECK FAILED: %s | %s | %s\n' "$file" "$rule" "$line"
    done < /tmp/jarvis_privacy_matches.txt
    failures=$((failures + 1))
  fi
}

while IFS= read -r file; do
  [ -f "$file" ] || continue
  allow_file "$file" || continue

  case "$file" in
    *.png|*.jpg|*.jpeg|*.gif|*.webp|*.ico|*.pdf|*.zip|*.gz|*.tar) continue ;;
  esac

  check_pattern "$file" "ssh private key header" '-----BEGIN (OPENSSH|RSA|DSA|EC|PRIVATE) KEY-----'
  check_pattern "$file" "ssh public key material" 'ssh-ed25519[[:space:]]+[A-Za-z0-9+/=]+'
  check_pattern "$file" "hardcoded password assignment" '(^|[^A-Z0-9_])(password|passwd)[[:space:]]*=[[:space:]]*[^[:space:]\"'\''<>{}][^#[:space:]]+'
  check_pattern "$file" "hardcoded token assignment" '(^|[^A-Z0-9_])(token|api_key|secret)[[:space:]]*=[[:space:]]*[^[:space:]\"'\''<>{}][^#[:space:]]+'
  check_pattern "$file" "home directory path" '/home/[A-Za-z0-9._-]+'
  check_pattern "$file" "personal deployment wording" 'Dennis|serverhub|dennishub|Recommended install on Dennis'
  check_pattern "$file" "private LAN IP" '(^|[^0-9])(192\.168\.[0-9]{1,3}\.[0-9]{1,3}|10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[0-1])\.[0-9]{1,3}\.[0-9]{1,3})([^0-9]|$)'
  check_pattern "$file" "specific service inventory" 'jellyfin|jellyseerr|adguardhome|homeassistant|sonarr|radarr|readarr|prowlarr|homarr|minecraft|scrypted|uisp'
  check_pattern "$file" "service-specific dependency example in code" 'qbittorrent|gluetun'

done < <(git ls-files)

rm -f /tmp/jarvis_privacy_matches.txt

if [ "$failures" -gt 0 ]; then
  echo "Privacy check failed with ${failures} rule group hit(s)."
  exit 1
fi

echo "Privacy check OK: tracked files contain no blocked private deployment patterns."
