#!/usr/bin/env python3
"""Build a validated *non-flashable* M55 UN1CA stock partition staging manifest.

Inputs are artifacts from the successful Samsung Bifrost extraction, not
firmware guesses. This is not a boot test and does not sign or flash images.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

STOCK = {
    "vendor": (2008227840, "825c78c6855e837b07d65e6e30d30959ef2caab43bf7eaeb12a305d0f8a34203"),
    "odm": (1699840, "a6520727edcb70a1119368538d9ba566f571d71b300963ffcf819947db075f82"),
    "vendor_dlkm": (126201856, "e52e39b4b5443d398528c21a483757c3af673a29d39ba46bd086d17361d92ae4"),
}
PATCHED_KERNEL_SHA = {
    "boot.img": "937a4c973ff7daff7fcc63c6244526be9b11a69b4a7d2729c39661fd9ccf4479",
    "vendor_boot.img": "dd0ac56f3d186ce0545f47352ce2db4ff09221c7654bf7236f9c1a1bae5c719c",
    "dtbo.img": "b83bb40ac00a9e4e4855a6c47527326a17b681fb5af840153ea69726e2898b2b",
    "vendor_dlkm.img": "1fa2a5f271b7f3ac4b9c61631065472015ca507821281dbbaa3f2519d037e37c",
}
SUPER_BYTES = 13631488000
GROUP_BYTES = 13627293696
STOCK_PARTITIONS = {
    "system": 6131326976, "product": 2054823936,
    "system_ext": 345051136, "vendor": 2008227840,
    "odm": 1699840, "vendor_dlkm": 126201856,
}
REQUIRED_FSTAB = {"system", "vendor", "product", "system_ext", "odm", "vendor_dlkm"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_props(text: str) -> dict[str, str]:
    return {k.strip(): v.strip() for line in text.splitlines()
            if "=" in line and not line.lstrip().startswith("#")
            for k, v in [line.split("=", 1)]}


def fail(message: str):
    raise SystemExit("M55_STAGE_ERROR: " + message)


def main():
    raw, metadata, out = map(Path, sys.argv[1:4])
    out.mkdir(parents=True, exist_ok=True)
    if not (metadata / "detailed/dynamic_partition_images.json").exists():
        fail("Missing audit metadata from successful M55 One UI 7 GitHub run")

    recorded = json.loads((metadata / "detailed/dynamic_partition_images.json").read_text())
    audit = json.loads((metadata / "detailed/vendor_odm_report.json").read_text())
    result = {
        "device": "m55xq", "model": "SM-M556B", "region": "INS",
        "build": "M556BXXS4BYH2", "android_version": "15",
        "status": "STOCK_PARTITIONS_VERIFIED_NOT_FLASHABLE",
        "super_size": SUPER_BYTES, "group": "qti_dynamic_partitions",
        "group_maximum_size": GROUP_BYTES,
        "physical_partitions": {}, "stock_logical_partitions": STOCK_PARTITIONS,
        "kernel_images_included": False,
        "warnings": [
            "This is NOT a bootable UN1CA One UI 8 ROM or flashable super.",
            "S22 donor system/product has not been integrated.",
            "Patched boot/vendor_boot/dtbo/vendor_dlkm not available in this CI job.",
            "Stock vbmeta must not be flashed with patched boot images.",
        ],
    }

    for name, (expected_length, expected_hash) in STOCK.items():
        p = raw / (name + ".img")
        if not p.is_file():
            fail("Missing stock logical partition: " + str(p))
        if p.stat().st_size != expected_length:
            fail(f"{name}: size mismatch, expected {expected_length}, got {p.stat().st_size}")
        if sha256(p) != expected_hash:
            fail(name + ": SHA256 mismatch with verified Samsung stock")
        with p.open("rb") as f:
            f.seek(1024)
            magic = f.read(4).hex()
        if magic != "e2e1f5e0":
            fail(name + ": expected EROFS filesystem")
        if name not in recorded or recorded[name]["sha256"] != expected_hash:
            fail(name + ": disagreement with prior extraction report")
        result["physical_partitions"][name] = {
            "bytes": expected_length, "sha256": expected_hash,
            "filesystem": "EROFS", "files": audit[name]["files"],
        }
        print("M55_STAGE_PARTITION_OK", name, expected_length, flush=True)

    expected_vendor = "m55xq"
    props = parse_props((metadata / "detailed/stock_configs/vendor/build.prop").read_text())
    if props.get("ro.product.vendor.device") != expected_vendor:
        fail("The stored vendor is not Galaxy M55")
    if props.get("ro.product.vendor.model") != "SM-M556B":
        fail("The stored vendor has wrong Samsung model")
    if props.get("ro.board.api_level") != "31":
        fail("Unexpected M55 board API level")
    if props.get("ro.product.first_api_level") != "34":
        fail("Unexpected M55 product first API level")
    result["board_api_level"] = 31
    result["product_first_api_level"] = 34
    result["vendor_sdk"] = props.get("ro.vendor.build.version.sdk")
    result["vendor_platform"] = props.get("ro.board.platform")

    fstab = (metadata / "detailed/stock_configs/vendor/etc/fstab.qcom").read_text()
    fs_paths = set()
    for line in fstab.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 4:
            continue
        if "logical" in fields[-1]:
            fs_paths.add(fields[1].removeprefix("/"))
    missing = REQUIRED_FSTAB - fs_paths
    if missing:
        fail("Stock vendor fstab missing logical partitions: " + ",".join(sorted(missing)))
    result["fstab_logical_mounts"] = sorted(fs_paths)

    actual_stock_total = sum(STOCK_PARTITIONS.values())
    if actual_stock_total > GROUP_BYTES:
        fail("Stock LP partition sizes exceed measured group capacity")
    result["stock_allocated_bytes"] = actual_stock_total
    result["stock_remaining_group_bytes"] = GROUP_BYTES - actual_stock_total

    # The source donor must be validated at build time. These numbers are for
    # stock Android 15 only, not a promise One UI 8 fits.
    avb = json.loads((metadata / "detailed/avb_report.json").read_text())
    if sorted(x["file"] for x in avb) != ["vbmeta.img", "vbmeta_system.img"]:
        fail("Missing original Samsung AVB metadata")
    if any(x["flags"] != 0 for x in avb):
        fail("Unexpected Samsung AVB flags")
    result["stock_vbmeta_descriptor_counts"] = {x["file"]: len(x["descriptors"]) for x in avb}

    (out / "m55_stage0.json").write_text(json.dumps(result, indent=2) + "\n")
    (out / "DO_NOT_FLASH.txt").write_text(
        "UN1CA M55 Stage 0: STOCK VENDOR GEOMETRY VALIDATION ONLY\n"
        "This output is not a ROM, boot image, or signed flashable package.\n"
        "No donor system/product or patched boot chain is included.\n"
        "Source Galaxy M55 One UI 7 M556BXXS4BYH2 / INS.\n"
        "Do not flash stock AVB metadata with modified boot images.\n"
    )
    print("M55_STAGE0_BUILD_VALIDATED", flush=True)
    for name, value in [
        ("stock LP total", actual_stock_total),
        ("group headroom", result["stock_remaining_group_bytes"]),
        ("super bytes", SUPER_BYTES),
    ]:
        print("M55_STAGE0_GEOMETRY", name, value, flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("### M55 Stage 0: verified stock partition assembly input\n")
            f.write(f"- Vendor, ODM, vendor_dlkm: hashes and EROFS verified\n")
            f.write(f"- Remaining LP group bytes in STOCK layout: `{result['stock_remaining_group_bytes']}`\n")
            f.write("- Not bootable; donor One UI 8 and tested modified boot chain still required\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
