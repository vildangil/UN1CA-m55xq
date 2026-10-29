#!/usr/bin/env python3
"""Audit remaining UN1CA target configuration requirements without guessing M55 SEC flags."""
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])
gen = (root / "scripts/internal/gen_config_file.sh").read_text()
target = (root / "target/m55xq/config.sh").read_text()
platform = (root / "platform/sm7450/config.sh").read_text()
# Only literal GET_BUILD_VAR names in the generator; optional defaults are skipped.
needed = set()
for line in gen.splitlines():
    match = re.match(r'^\s+GET_BUILD_VAR "(TARGET_[A-Z0-9_]+)"\s*$', line)
    if match:
        needed.add(match.group(1))
defined = set(re.findall(r'^\s*(TARGET_[A-Z0-9_]+)=', target + "\n" + platform,
                         flags=re.MULTILINE))
missing = sorted(needed - defined)
# These need a nonempty runtime value, not just an environment fallback variable.
known_empty = []
for name in sorted(needed & defined):
    rx = re.compile(r'^' + re.escape(name) + r'=\s*"\$\{[^}]+:-\}"\s*$',
                    flags=re.MULTILINE)
    if rx.search(target + "\n" + platform):
        known_empty.append(name)

report = {
    "target": "m55xq",
    "required_literal_variables": len(needed),
    "missing_feature_definitions": missing,
    "empty_by_default": known_empty,
    "build_is_flash_ready": False,
    "scope": "static preflight of committed target config only; the full CI build now attempts stock-derived values after extracting exact M556BXXS4BYH2",
    "stock_automatic_feature_probe": "scripts/m55_derive_features.py",
    "remedy": "Run manual CI build to collect real M55 floating_feature.xml and policy evidence; unknown features block make_rom. Verify kernel/AVB, VINTF and donor compatibility before any flash.",
}
out.mkdir(parents=True, exist_ok=True)
(out / "m55_build_readiness.json").write_text(json.dumps(report, indent=2) + "\n")
print("M55_BUILD_REQUIRED_FIELDS", len(needed), flush=True)
print("M55_BUILD_MISSING_FIELDS", len(missing), flush=True)
print("M55_BUILD_EMPTY_BY_DEFAULT", " ".join(known_empty), flush=True)
for name in missing:
    print("M55_MISSING_CONFIG", name, flush=True)
if not missing and not known_empty:
    print("M55_BUILD_CONFIG_DEFINITIONS_COMPLETE", flush=True)
else:
    print("M55_BUILD_BLOCKED_BY_UNVERIFIED_CONFIG", flush=True)
