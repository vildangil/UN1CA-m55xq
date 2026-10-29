#!/usr/bin/env bash
# Fetch a *pinned* M55 One UI 7 archive on the GitHub runner, not on the PC.
# Does NOT extract BL, patch AVB, or write to a connected device.
set -euo pipefail

if [[ -z "${M55_ONEUI7_URL:-}" ]]; then
    echo "Add repository secret M55_ONEUI7_URL (temporary direct AP or full ZIP link)." >&2
    exit 1
fi
[[ "$M55_ONEUI7_URL" == https://* ]] || {
    echo "M55_ONEUI7_URL must use HTTPS" >&2
    exit 1
}
if [[ -n "${M55_ONEUI7_SHA256:-}" && ! "$M55_ONEUI7_SHA256" =~ ^[[:xdigit:]]{64}$ ]]; then
    echo "Invalid M55_ONEUI7_SHA256 secret" >&2
    exit 1
fi

DEST="${RUNNER_TEMP:-/tmp}/M556BXXS4BYH2.zip"
REPORT="${GITHUB_WORKSPACE:-.}/m55-oneui7-report.txt"
# Do not echo the temporary signed link into public workflow logs.
echo "Downloading M556BXXS4BYH2 archive to ephemeral GitHub runner..."
curl --fail --location --silent --show-error \
    --retry 4 --retry-all-errors --retry-delay 8 \
    --connect-timeout 30 --continue-at - \
    --output "$DEST" "$M55_ONEUI7_URL"

echo "Checking ZIP container..."
unzip -tq "$DEST" >/dev/null || { echo "Downloaded file is not a valid ZIP" >&2; exit 1; }
CONTENTS="$(unzip -Z -1 "$DEST")"
if ! grep -Eq '(^|/)AP_M556BXXS4BYH2_[^/]*\.tar\.md5$' <<< "$CONTENTS"; then
    echo "Expected AP_M556BXXS4BYH2...tar.md5 missing: refusing wrong firmware" >&2
    exit 1
fi
SUM="$(sha256sum "$DEST" | cut -d' ' -f1)"
if [[ -n "${M55_ONEUI7_SHA256:-}" && "${SUM,,}" != "${M55_ONEUI7_SHA256,,}" ]]; then
    echo "M55 archive SHA-256 mismatch" >&2
    exit 1
fi
{
    echo "Model: SM-M556B"
    echo "Requested firmware: M556BXXS4BYH2 (Android 15, One UI 7)"
    echo "Download bytes: $(stat -c '%s' "$DEST")"
    echo "SHA-256: $SUM"
    echo "Source: remote HTTPS link supplied as GitHub Secret (not logged)"
    echo "ZIP members:"
    printf '%s\n' "$CONTENTS"
    echo "Result: ZIP CRC valid; AP build filename matched; no phone flashing"
} > "$REPORT"
# Stream the AP tar listing directly from the ZIP. No second multi-GB AP copy.
echo "Reading AP partition list (streaming, no extraction)..."
python3 - "$DEST" "$REPORT" <<'PY'
import re
import sys
import tarfile
import zipfile
from pathlib import Path

zip_path, report_path = sys.argv[1:]
with zipfile.ZipFile(zip_path) as z:
    names = [name for name in z.namelist()
             if re.search(r"(?:^|/)AP_M556BXXS4BYH2_[^/]*\\.tar\\.md5$", name)]
    if not names:
        raise SystemExit("Missing expected AP entry")
    with z.open(names[0]) as inner:
        with tarfile.open(fileobj=inner, mode="r|") as tar:
            with open(report_path, "a", encoding="utf-8") as report:
                report.write("\\nAP tar members (name + stored length):\\n")
                for entry in tar:
                    if entry.isfile():
                        report.write(f"{entry.name} {entry.size}\\n")
PY
echo "PASS: verified M55 One UI 7 archive remotely"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    {
        echo "### M55 One UI 7 archive verified on GitHub"
        echo "- Exact AP build: \`M556BXXS4BYH2\`"
        echo "- SHA-256: \`$SUM\`"
        echo "- Full firmware was NOT uploaded as an artifact or flashed."
    } >> "$GITHUB_STEP_SUMMARY"
fi
