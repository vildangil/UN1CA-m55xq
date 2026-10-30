#!/usr/bin/env python3
"""Derive UN1CA M55 target SEC options from real Samsung stock firmware.

Only copies exact SEC_FLOATING_FEATURE keys and unique policy filenames;
it never borrows values from a donor device or guesses from model family.
An evidence manifest accompanies each value. CI cannot build the ROM if
some required settings are unsupported by the inspected firmware.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED = re.compile(r'^\s*GET_BUILD_VAR "(TARGET_[A-Z0-9_]+)"\s*$', re.M)
DEFINED = re.compile(r'^\s*(TARGET_[A-Z0-9_]+)\s*=', re.M)
VALID_KEY = re.compile(r"^TARGET_[A-Z0-9_]+$")
INTEGER_KEYS = {
    "TARGET_COMMON_CONFIG_MDNIE_MODE", "TARGET_LCD_CONFIG_COLOR_WEAKNESS_SOLUTION",
    "TARGET_LCD_CONFIG_CONTROL_AUTO_BRIGHTNESS",
    "TARGET_LCD_CONFIG_HFR_DEFAULT_REFRESH_RATE", "TARGET_LCD_CONFIG_HFR_MODE",
    "TARGET_RIL_SIM_CONFIG_MULTISIM_TRAYCOUNT",
    "TARGET_WLAN_CONFIG_CONNECTION_PERSONALIZATION",
    "TARGET_WLAN_CONFIG_CPU_CSTATE_DISABLE_THRESHOLD",
    "TARGET_WLAN_CONFIG_DATA_ACTIVITY_AFFINITY_BOOSTER_THRESHOLD",
    "TARGET_WLAN_CONFIG_DYNAMIC_SWITCH",
    "TARGET_WLAN_CONFIG_L1SS_DISABLE_THRESHOLD",
}
BOOL_RE = re.compile(r"^(true|false)$", flags=re.I)
INT_RE = re.compile(r"^-?[0-9]+$")
NON_VALUES = {"", "null", "n/a", "undefined", "__M55_UNVERIFIED__"}

# Only used in an explicitly selected *non-flashable* CI experiment.
# These are inert compatibility placeholders, NOT statements about M55
# hardware. They must be listed in the uploaded evidence manifest.
EXPERIMENTAL_ENUM_DEFAULTS = {
    "TARGET_LCD_CONFIG_HFR_DEFAULT_REFRESH_RATE": "60",
    "TARGET_LCD_CONFIG_HFR_MODE": "0",
    "TARGET_LCD_CONFIG_COLOR_WEAKNESS_SOLUTION": "0",
    "TARGET_LCD_CONFIG_CONTROL_AUTO_BRIGHTNESS": "0",
    "TARGET_RIL_SIM_CONFIG_MULTISIM_TRAYCOUNT": "1",
}
EXPERIMENTAL_NUMERIC_DEFAULTS = {
    "TARGET_COMMON_CONFIG_MDNIE_MODE": "0",
    "TARGET_WLAN_CONFIG_CONNECTION_PERSONALIZATION": "0",
    "TARGET_WLAN_CONFIG_CPU_CSTATE_DISABLE_THRESHOLD": "0",
    "TARGET_WLAN_CONFIG_DATA_ACTIVITY_AFFINITY_BOOSTER_THRESHOLD": "0",
    "TARGET_WLAN_CONFIG_DYNAMIC_SWITCH": "0",
    "TARGET_WLAN_CONFIG_L1SS_DISABLE_THRESHOLD": "0",
}

def experimental_placeholder(key: str) -> str:
    """Syntactically typed, minimally enabled placeholder for a preview only."""
    if key in EXPERIMENTAL_ENUM_DEFAULTS:
        return EXPERIMENTAL_ENUM_DEFAULTS[key]
    if key in EXPERIMENTAL_NUMERIC_DEFAULTS:
        return EXPERIMENTAL_NUMERIC_DEFAULTS[key]
    if "_SUPPORT_" in key:
        return "false"
    # Do not copy S22's policy filenames or fingerprint hardware identity.
    if "_CONFIG_" in key:
        return "none"
    raise ValueError("No explicit experimental placeholder for " + key)



def stock_property(path: Path) -> dict[str, str]:
    result = {}
    if path.is_file():
        for line in path.read_text(errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                result[k.strip()] = v.strip()
    return result


def collect_floating(root: Path):
    """Read only unambiguous exact feature tags in stock images."""
    possible = []
    for partition in ("system", "product", "vendor", "odm"):
        candidate = root / partition
        if candidate.is_dir():
            possible += list(candidate.rglob("floating_feature.xml"))
    evidence = {}
    errors = []
    for file in sorted(set(possible)):
        try:
            tree = ET.parse(file)
        except ET.ParseError as exc:
            errors.append(f"Malformed {file.relative_to(root)}: {exc}")
            continue
        for element in tree.iter():
            tag = element.tag.rsplit("}", 1)[-1].strip()
            if not tag.startswith("SEC_FLOATING_FEATURE_"):
                continue
            val = (element.text or "").strip()
            if val.lower() in NON_VALUES:
                continue
            evidence.setdefault(tag, []).append((val, str(file.relative_to(root))))
    return evidence, errors


def lookup(evidence, tag):
    values = evidence.get(tag, [])
    if not values:
        return None, None
    norm = {v.lower(): v for v, _ in values}
    if len(norm) > 1:
        return None, f"Conflicting firmware values for {tag}: {values}"
    return values[0][0], " | ".join(sorted(set(p for _, p in values)))


def parse_stock(root: Path, repo: Path):
    system_props = stock_property(root / "system/system/build.prop")
    vendor_props = stock_property(root / "vendor/build.prop")
    # Vendor Android 12 BSP with updated One UI 7 system is expected for M55.
    if vendor_props.get("ro.product.vendor.device") != "m55xq":
        raise ValueError("Not a verified M55 vendor: ro.product.vendor.device != m55xq")
    if vendor_props.get("ro.product.first_api_level") != "34":
        raise ValueError("Not the inspected SM-M556B launch API")
    if vendor_props.get("ro.board.api_level") != "31":
        raise ValueError("Unexpected M55 board API level")
    if vendor_props.get("ro.vendor.build.version.incremental") != "M556BXXS4BYH2":
        raise ValueError("Wrong stock M55 firmware; expected exact M556BXXS4BYH2")

    gen = (repo / "scripts/internal/gen_config_file.sh").read_text()
    target = (repo / "target/m55xq/config.sh").read_text()
    platform = (repo / "platform/sm7450/config.sh").read_text()
    required = set(REQUIRED.findall(gen))
    explicitly_set = set(DEFINED.findall(target + "\n" + platform))
    needed = sorted(required - explicitly_set)
    optional = {
        "TARGET_AUDIO_CONFIG_RECORDALIVE_LIB_VERSION",
        "TARGET_LCD_CONFIG_HFR_SUPPORTED_REFRESH_RATE",
        "TARGET_LCD_CONFIG_HFR_SUPPORTED_REFRESH_RATE_NS",
        "TARGET_LCD_CONFIG_SEAMLESS_BRT",
        "TARGET_LCD_CONFIG_SEAMLESS_LUX",
        "TARGET_RIL_FEATURES", "TARGET_WLAN_CONFIG_CUSTOM_BACKOFF",
        "TARGET_WLAN_CONFIG_SEPARATE_ANT_BACKOFF",
        "TARGET_WLAN_CONFIG_SINGLE_ANT_BACKOFF",
        "TARGET_SECURITY_CONFIG_ESE_CHIP_VENDOR",
        "TARGET_SECURITY_CONFIG_ESE_COS_NAME",
    }

    features, xml_errors = collect_floating(root)
    found, provenance, conflicts, missing = {}, {}, [], []
    for key in sorted(set(needed) | optional):
        if not VALID_KEY.fullmatch(key):
            raise ValueError("Unexpected target name " + key)
        tag = "SEC_FLOATING_FEATURE_" + key.removeprefix("TARGET_")
        value, source = lookup(features, tag)
        if value is None:
            if source:
                conflicts.append(source)
            if key in needed:
                missing.append(key)
            continue
        if "_SUPPORT_" in key or key.endswith("_SUPPORT_ESEK"):
            if not BOOL_RE.fullmatch(value):
                if key in needed: missing.append(key)
                conflicts.append(f"Non-boolean {tag}={value!r} in {source}")
                continue
            value = value.lower()
        elif key in INTEGER_KEYS:
            if not INT_RE.fullmatch(value):
                if key in needed: missing.append(key)
                conflicts.append(f"Non-integer {tag}={value!r} in {source}")
                continue
        if "\n" in value or "\r" in value or "\0" in value:
            if key in needed: missing.append(key)
            conflicts.append(f"Unsafe value for {tag}")
            continue
        found[key] = value
        provenance[key] = {"value": value, "source": source, "key": tag, "method": "exact_xml_tag"}

    # Only derive filename selectors when a single matching policy can be
    # positively found in the unpacked TARGET firmware and is not ambiguous.
    policy_specs = {
        "TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME": "dvfs_policy_*.xml",
        "TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME": "siop_*.xml",
    }
    for key, pattern in policy_specs.items():
        if key in found:
            continue
        candidates = []
        for part in ("system", "product", "vendor"):
            base = root / part
            if base.is_dir():
                candidates += list(base.rglob(pattern))
        unique = sorted(set(p.stem for p in candidates))
        if len(unique) == 1:
            found[key] = unique[0]
            provenance[key] = {
                "value": unique[0],
                "source": str(candidates[0].relative_to(root)),
                "method": "unique_policy_filename",
            }
            if key in missing: missing.remove(key)
        elif len(unique) > 1:
            conflicts.append(f"Ambiguous {pattern}: {unique}")

    # Detect the camera/audio capabilities only when Samsung's config actually
    # exposes the corresponding exact key (do not infer from HAL existence).
    remaining = sorted(set(needed) - set(found))
    report = {
        "model": "SM-M556B", "firmware": "M556BXXS4BYH2",
        "vendor_device": "m55xq", "vendor_sdk": vendor_props.get("ro.vendor.build.version.sdk"),
        "system_sdk": system_props.get("ro.build.version.sdk"),
        "required_total": len(needed), "verified_count": len(set(needed)&set(found)),
        "verified_values": provenance,
        "missing_required": remaining,
        "xml_parse_errors": xml_errors, "conflicts": conflicts,
        "full_unica_build_unblocked": not remaining and not conflicts and not xml_errors,
        "boot_tested": False, "safe_to_flash": False,
    }
    return found, report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stock_root", type=Path, help="out/fw/SM-M556B_INS")
    p.add_argument("repo_root", type=Path)
    p.add_argument("output_dir", type=Path)
    p.add_argument("--fail-on-missing", action="store_true")
    p.add_argument("--experimental-preview", action="store_true",
                   help="Permit typed, visibly unverified placeholders ONLY for unflashable target-files analysis")
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    found, report = parse_stock(args.stock_root, args.repo_root)
    report["feature_policy"] = "experimental-preview" if args.experimental_preview else "strict"
    report["original_missing_required"] = list(report["missing_required"])
    report["experimental_placeholders"] = {}
    if args.experimental_preview:
        # Every unsupported flag is recorded, never disguised as stock evidence.
        # Conflicts are NOT resolved using the S22 donor.
        for key in report["missing_required"]:
            guessed = experimental_placeholder(key)
            found[key] = guessed
            report["experimental_placeholders"][key] = {
                "value": guessed,
                "verified": False,
                "reason": "No unambiguous M55 stock evidence; preview-only neutral default",
            }
        report["may_build_experimental_target_files"] = True
        report["full_unica_build_unblocked"] = False
        report["safe_to_flash"] = False
        report["boot_tested"] = False
    else:
        report["may_build_experimental_target_files"] = False
    config_path = args.output_dir / "m55-derived-features.sh"
    lines = [
        "# M55 features from M556BXXS4BYH2 stock; see m55-feature-evidence.json.",
        "# EXPERIMENTAL preview values are marked UNVERIFIED in the JSON report.",
        "# NOT VALIDATED FOR FLASHING; no automatic installation.",
    ]
    if args.experimental_preview:
        lines.append("M55_EXPERIMENTAL_FEATURES_ACTIVE=true")
    for key in sorted(found):
        lines.append(f"{key}={shlex.quote(found[key])}")
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (args.output_dir / "m55-feature-evidence.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("M55_STOCK_FEATURES_VERIFIED", report["verified_count"], "/", report["required_total"], flush=True)
    for item in report["missing_required"]:
        print("M55_FEATURE_UNVERIFIED", item, flush=True)
    for problem in report["xml_parse_errors"] + report["conflicts"]:
        print("M55_FEATURE_EVIDENCE_WARNING", problem, flush=True)
    if report["experimental_placeholders"]:
        print("M55_EXPERIMENTAL_PREVIEW_ONLY_UNVERIFIED_SETTINGS",
              len(report["experimental_placeholders"]), flush=True)
        print("M55_DO_NOT_FLASH_EXPERIMENTAL_HARDWARE_FEATURES", flush=True)
    if args.fail_on_missing and not report["full_unica_build_unblocked"] and not args.experimental_preview:
        sys.exit("M55_CONFIG_INCOMPLETE: See m55-feature-evidence.json; select explicit experimental preview to study downstream build steps")


if __name__ == "__main__":
    main()
