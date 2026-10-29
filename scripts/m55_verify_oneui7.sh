#!/usr/bin/env bash
# A pinned, user-provided Samsung M55 One UI 7 archive, NOT a FUS latest download.
set -euo pipefail
if [[ -z "${M55_ONEUI7_URL:-}" || -z "${M55_ONEUI7_SHA256:-}" ]]; then
    echo "Configure repository secrets M55_ONEUI7_URL and M55_ONEUI7_SHA256" >&2
    exit 1
fi
[[ "$M55_ONEUI7_URL" == https://* ]] || { echo "Only HTTPS firmware URLs are allowed" >&2; exit 1; }
[[ "$M55_ONEUI7_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "Invalid expected SHA-256" >&2; exit 1; }

DEST="${RUNNER_TEMP:-/tmp}/m55-oneui7-stock.zip"
curl --fail --location --silent --show-error --connect-timeout 30 \
    --output "$DEST" "$M55_ONEUI7_URL"
printf '%s  %s\n' "$M55_ONEUI7_SHA256" "$DEST" | sha256sum --check --status || {
    echo "M55 archive SHA-256 mismatch" >&2
    exit 1
}
unzip -tq "$DEST" >/dev/null || { echo "Invalid M55 firmware ZIP" >&2; exit 1; }
if ! unzip -Z -1 "$DEST" | grep -Eq '(^|/)AP_.*\.tar\.md5$'; then
    echo "No AP_*.tar.md5 inside supplied firmware ZIP" >&2
    exit 1
fi
echo "PASS: M55 stock ZIP integrity and archive layout"
echo "WARNING: CRC/SHA verification does not itself prove One UI 7 version."
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    echo "### M55 pinned One UI 7 archive" >> "$GITHUB_STEP_SUMMARY"
    echo "SHA-256 and ZIP integrity passed; firmware version still needs inspection." >> "$GITHUB_STEP_SUMMARY"
fi
