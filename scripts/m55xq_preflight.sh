#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mapfile -t targets < <(find "$ROOT/target" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
[[ "${#targets[@]}" == 1 && "${targets[0]}" == m55xq ]] || { echo "Expected only m55xq, got: ${targets[*]}"; exit 1; }
[[ -f "$ROOT/platform/sm7450/config.sh" ]] || exit 1
while IFS= read -r -d '' f; do bash -n "$f"; done < <(find "$ROOT/target/m55xq" "$ROOT/platform/sm7450" -name '*.sh' -print0)
echo "PASS: M55-only tree and bash syntax"
if [[ "${1:-}" == --images ]]; then
  IMAGES="${M55_KERNEL_DIR:-$ROOT/out/m55xq-kernel}"
  python3 - "$IMAGES" <<'PY'
from pathlib import Path
import sys,hashlib
root=Path(sys.argv[1])
for name,offset,magic in (
 ("boot.img",0,bytes.fromhex("414e44524f494421")),
 ("vendor_boot.img",0,bytes.fromhex("564e4452424f4f54")),
 ("dtbo.img",0,bytes.fromhex("d7b7ab1e")),
 ("vendor_dlkm.img",1024,bytes.fromhex("e2e1f5e0"))):
 p=root/name
 if not p.is_file(): raise SystemExit(f"missing: {p}")
 with p.open("rb") as f:
  f.seek(offset)
  if f.read(len(magic))!=magic:raise SystemExit(f"bad magic: {p}")
 h=hashlib.sha256()
 with p.open("rb") as f:
  for block in iter(lambda:f.read(1048576),b""): h.update(block)
 print(name,p.stat().st_size,h.hexdigest())
PY
fi
