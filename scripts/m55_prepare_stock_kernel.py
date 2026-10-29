#!/usr/bin/env python3
"""Prepare custom-binary copies of pinned M556BXXS4BYH2 stock boot images.

Uses the owner's original samsung_custom_binary.py without changing it.
Never changes the extracted stock files. No vbmeta/system or bootloader patch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from m55.samsung_custom_binary import SIGNER_MAGIC, customize, detect_type, parse_avb_footer

SOURCE = {
    "boot.img": (100663296, "e84ccd196731d16eb745619bd8ecd4ae2d37e644cdd8822855b36577d4c1e979"),
    "vendor_boot.img": (100663296, "04871187eaf09053cabe1486c1838ef2f4cd34a41f4283400224d5a35ae65126"),
    "dtbo.img": (8388608, "5086afb98fdc592e8e248ee51842590e7ead5e3fbb9c12e58e9132eee632add2"),
    "vendor_dlkm.img": (126201856, "e52e39b4b5443d398528c21a483757c3af673a29d39ba46bd086d17361d92ae4"),
}
# SHA-256 measured by executing the owner's supplied tool against the exact
# stock images from successful GitHub Actions M55 inspection #40908265068.
OUTPUT = {
    "boot.img": "6924a9cc6e5732aab897e46e6af8133edbe95fcf01de659e2d8318e62d456729",
    "vendor_boot.img": "9a9344bccf712e5a6605085388f0ebd470a3953b75ef70e9087a695e403f9c41",
    "dtbo.img": "f0c1e70c7b3eb0db054bd6cd96a26226f8274cdb17989d9d0b5f20316ea7387e",
    "vendor_dlkm.img": SOURCE["vendor_dlkm.img"][1],
}


def sha256(path: Path) -> str:
    hash = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(4 * 1024 * 1024), b""):
            hash.update(part)
    return hash.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kernel-dir", type=Path, required=True,
                    help="Original extracted M55 stock kernel directory")
    ap.add_argument("--vendor-dlkm", type=Path, required=True,
                    help="Preserved stock M55 vendor_dlkm.img before upstream extraction deletes it")
    ap.add_argument("--output-dir", type=Path, required=True,
                    help="Output directory for separately patched copies")
    args = ap.parse_args()
    stock = args.kernel_dir
    output = args.output_dir
    if output.resolve() == stock.resolve() or stock.resolve() in output.resolve().parents:
        ap.error("Output must be separate from original extracted firmware")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "device": "m55xq",
        "model": "SM-M556B",
        "firmware": "M556BXXS4BYH2",
        "method": "original user-provided samsung_custom_binary.py (SignerVer02)",
        "input_mode": "pinned_stock",
        "partitions": {},
        "bootloader_modified": False,
        "vbmeta_system_modified": False,
        "flash_tested": False,
    }
    for name, (size, expected_sha) in SOURCE.items():
        src = args.vendor_dlkm if name == "vendor_dlkm.img" else stock / name
        if not src.is_file() or src.stat().st_size != size:
            raise ValueError(f"{name}: original stock size mismatch or file missing")
        if sha256(src) != expected_sha:
            raise ValueError(f"{name}: SHA-256 mismatch; refuse to patch unknown firmware")
        dst = output / name
        if src.resolve() == dst.resolve():
            raise ValueError("Refusing to rewrite stock image in-place")
        if name == "vendor_dlkm.img":
            with src.open("rb") as f:
                f.seek(1024)
                if f.read(4) != bytes.fromhex("e2e1f5e0"):
                    raise ValueError("Stock vendor_dlkm lacks expected EROFS signature")
            shutil.copyfile(src, dst)
            patch_info = {"type":"vendor_dlkm", "action":"stock_image_kept_unchanged"}
        else:
            source_data = src.read_bytes()
            if SIGNER_MAGIC not in source_data:
                raise ValueError(name + ": SignerVer02 not present; tool is intentionally non-idempotent")
            result, patch_info = customize(source_data)
            if len(result) != len(source_data):
                raise ValueError(name + ": patch unexpectedly changed partition image length")
            if SIGNER_MAGIC in result:
                raise ValueError(name + ": signer marker remains in output")
            if name != "dtbo.img":
                before = parse_avb_footer(source_data)
                after = parse_avb_footer(result)
                if not before or not after or before["vbmeta_size"] != after["vbmeta_size"]:
                    raise ValueError(name + ": AVB vbmeta metadata not preserved")
                old = source_data[before["vbmeta_offset"]:
                                  before["vbmeta_offset"] + before["vbmeta_size"]]
                new = result[after["vbmeta_offset"]:
                             after["vbmeta_offset"] + after["vbmeta_size"]]
                if old != new:
                    raise ValueError(name + ": AVB vbmeta bytes changed")
            dst.write_bytes(result)
            del result, source_data
        actual_output_sha = sha256(dst)
        if actual_output_sha != OUTPUT[name]:
            dst.unlink(missing_ok=True)
            raise ValueError(f"{name}: custom-binary output hash changed: {actual_output_sha}")
        manifest["partitions"][name] = {
            "source_sha256":expected_sha,
            "output_sha256":actual_output_sha,
            "bytes":size,
            "patch_info":patch_info
        }
        print("M55_STOCK_CUSTOM_BINARY_READY", name, actual_output_sha,flush=True)
    (output / "stock_custom_binary_report.json").write_text(
        json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print("M55_STOCK_CUSTOM_BINARY_ALL_VERIFIED",flush=True)


if __name__ == "__main__":
    main()
