#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/runner"

cat > "$TMP/bin/curl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
OUT=""
while [[ "$#" -gt 0 ]]; do
    if [[ "$1" == "--output" ]]; then
        OUT="$2"
        shift 2
    else
        shift
    fi
done
if [[ "${TEST_HTTP_STATUS:-}" == "403" ]]; then
    printf 403
    exit 22
fi
cp "$TEST_FIXTURE" "$OUT"
printf 200
SH
chmod +x "$TMP/bin/curl"

python3 - "$TMP/fixture.zip" <<'PY'
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import sys
import tarfile
raw = BytesIO()
with tarfile.open(fileobj=raw, mode="w") as t:
    content = b"dummy vendor partition"
    info = tarfile.TarInfo("vendor.img.lz4")
    info.size = len(content)
    t.addfile(info, BytesIO(content))
with ZipFile(sys.argv[1], "w", ZIP_DEFLATED) as z:
    z.writestr("AP_M556BXXS4BYH2_FAKE.tar.md5", raw.getvalue())
PY

set +e
TEST_HTTP_STATUS=403 TEST_FIXTURE="$TMP/fixture.zip" \
    M55_ONEUI7_URL="https://example.invalid/private?token=must-not-print" \
    RUNNER_TEMP="$TMP/runner" GITHUB_WORKSPACE="$TMP" \
    PATH="$TMP/bin:$PATH" bash "$ROOT/scripts/m55_verify_oneui7.sh" \
    > "$TMP/deny.log" 2>&1
RESULT=$?
set -e
[[ "$RESULT" == 22 ]] || { echo "Expected curl status 22, got $RESULT"; exit 1; }
grep -q 'HTTP 403' "$TMP/deny.log"
! grep -q 'must-not-print' "$TMP/deny.log"
echo "PASS: HTTP 403 fails immediately without leaking URL"

TEST_HTTP_STATUS=200 TEST_FIXTURE="$TMP/fixture.zip" \
    M55_ONEUI7_URL="https://example.invalid/good.zip" \
    RUNNER_TEMP="$TMP/runner" GITHUB_WORKSPACE="$TMP" \
    PATH="$TMP/bin:$PATH" bash "$ROOT/scripts/m55_verify_oneui7.sh" \
    > "$TMP/accept.log" 2>&1
grep -q 'AP tar members' "$TMP/m55-oneui7-report.txt"
grep -q 'vendor.img.lz4' "$TMP/m55-oneui7-report.txt"
echo "PASS: valid fixture ZIP and AP contents"
