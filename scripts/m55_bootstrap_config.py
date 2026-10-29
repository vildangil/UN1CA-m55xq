#!/usr/bin/env python3
"""Prepare temporary UN1CA dependencies-only M55 config.

Upstream gen_config_file.sh insists on a complete SEC feature table even
when merely building host tools. The placeholders here are explicitly
UNVERIFIED and MUST NOT be used for make_rom. CI regenerates its config
from genuine Samsung stock evidence and blocks if any required value is
missing. This file is a runner temporary artifact, never committed.
"""
import argparse
import re
from pathlib import Path

REQUIRED = re.compile(r'^\s*GET_BUILD_VAR "(TARGET_[A-Z0-9_]+)"\s*$', re.M)
DEFINED = re.compile(r'^\s*(TARGET_[A-Z0-9_]+)\s*=', re.M)
NUMERIC = {"TARGET_COMMON_CONFIG_MDNIE_MODE", "TARGET_LCD_CONFIG_HFR_MODE"}


def generate(root: Path) -> str:
    gen = (root / "scripts/internal/gen_config_file.sh").read_text()
    target = (root / "target/m55xq/config.sh").read_text()
    platform = (root / "platform/sm7450/config.sh").read_text()
    missing = sorted(set(REQUIRED.findall(gen)) -
                     set(DEFINED.findall(target + "\n" + platform)))
    rows = [
        "# TEMPORARY M55 bootstrap for host tools / stock extraction ONLY",
        "# All values below are deliberately unverified and may not be used by make_rom.",
        "M55_BOOTSTRAP_ONLY=true",
    ]
    for key in missing:
        value = "0" if key in NUMERIC else "__M55_UNVERIFIED__"
        rows.append(f'{key}="{value}"')
    return "\n".join(rows) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generate(args.root), encoding="utf-8")
    print("M55_BOOTSTRAP_ONLY_TEMP_CONFIG_READY", args.output)


if __name__ == "__main__":
    main()
