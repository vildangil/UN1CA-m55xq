#!/usr/bin/env python3
"""
samsung_custom_binary.py

Tested on Samsung SM-M556E boot/vendor_boot/dtbo images used in the
B4 / K5 / S4 downgrade experiment.

What it does:
  * detects boot.img, vendor_boot.img or dtbo.img;
  * removes the Samsung SignerVer02 block and its signed tail;
  * for boot/vendor_boot, preserves the existing AVB vbmeta blob and
    relocates it directly after the real payload, then updates the AVB footer;
  * for dtbo, keeps the real DTBO payload byte-for-byte and zeros the tail.

This does NOT forge Samsung RP 004 -> 005 and does NOT modify the bootloader.
It relies on an unlocked bootloader accepting the image as a custom binary.

Use at your own risk. Always keep known-good boot/vendor_boot/dtbo backups.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

SIGNER_MAGIC = b"SignerVer02"
AVB_FOOTER_MAGIC = b"AVBf"
BOOT_MAGIC = b"ANDROID!"
VENDOR_BOOT_MAGIC = b"VNDRBOOT"
DTBO_MAGIC = 0xD7B7AB1E
AVB_FOOTER_SIZE = 64


def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_avb_footer(data: bytes) -> dict | None:
    if len(data) < AVB_FOOTER_SIZE:
        return None
    f = data[-AVB_FOOTER_SIZE:]
    if f[:4] != AVB_FOOTER_MAGIC:
        return None
    magic, major, minor, original_size, vbmeta_offset, vbmeta_size, reserved = \
        struct.unpack(">4sIIQQQ28s", f)
    if vbmeta_offset + vbmeta_size > len(data):
        raise ValueError("AVB footer points outside the image")
    return {
        "magic": magic,
        "major": major,
        "minor": minor,
        "original_size": original_size,
        "vbmeta_offset": vbmeta_offset,
        "vbmeta_size": vbmeta_size,
        "reserved": reserved,
    }


def make_avb_footer(old_footer: dict, original_size: int,
                    vbmeta_offset: int, vbmeta_size: int) -> bytes:
    return struct.pack(
        ">4sIIQQQ28s",
        old_footer["magic"],
        old_footer["major"],
        old_footer["minor"],
        original_size,
        vbmeta_offset,
        vbmeta_size,
        old_footer["reserved"],
    )


def detect_type(data: bytes) -> str:
    if data.startswith(BOOT_MAGIC):
        return "boot"
    if data.startswith(VENDOR_BOOT_MAGIC):
        return "vendor_boot"
    if len(data) >= 4 and struct.unpack(">I", data[:4])[0] == DTBO_MAGIC:
        return "dtbo"
    raise ValueError("Unknown image type: expected boot, vendor_boot or dtbo")


def signer_info(data: bytes, signer_off: int) -> dict:
    block = data[signer_off:signer_off + 0x100]

    def cstr(off: int, size: int) -> str:
        raw = block[off:off + size].split(b"\0", 1)[0]
        return raw.decode("ascii", errors="replace")

    info = {}
    if len(block) >= 0x90:
        info["version_name"] = cstr(0x20, 0x20)
        info["model_name"] = cstr(0x50, 0x20)
        info["system_rp"] = cstr(0x70, 0x10)
        info["kernel_rp"] = cstr(0x80, 0x10)
    return info


def customize_dtbo(data: bytes) -> tuple[bytes, dict]:
    if len(data) < 8:
        raise ValueError("DTBO image too small")

    magic, total_size = struct.unpack(">II", data[:8])
    if magic != DTBO_MAGIC:
        raise ValueError("Bad DTBO magic")
    if not (0 < total_size <= len(data)):
        raise ValueError(f"Invalid DTBO total_size: 0x{total_size:x}")

    signer_off = data.find(SIGNER_MAGIC)
    if signer_off < 0:
        raise ValueError("SignerVer02 not found")
    if signer_off != total_size:
        raise ValueError(
            f"Unexpected DTBO layout: SignerVer02 at 0x{signer_off:x}, "
            f"but DTBO total_size is 0x{total_size:x}"
        )

    out = bytearray(len(data))
    out[:total_size] = data[:total_size]

    return bytes(out), {
        "type": "dtbo",
        "payload_end": total_size,
        "signer_off": signer_off,
        "avb_preserved": False,
        **signer_info(data, signer_off),
    }


def customize_boot_or_vendor(data: bytes, image_type: str) -> tuple[bytes, dict]:
    signer_off = data.find(SIGNER_MAGIC)
    if signer_off < 0:
        raise ValueError("SignerVer02 not found")

    footer = parse_avb_footer(data)
    if footer is None:
        raise ValueError(
            "No AVB footer found. This conservative script only rewrites "
            "boot/vendor_boot layouts matching the tested SM-M556E images."
        )

    vbmeta_off = footer["vbmeta_offset"]
    vbmeta_size = footer["vbmeta_size"]
    if vbmeta_off < signer_off:
        raise ValueError("Unexpected layout: AVB vbmeta starts before SignerVer02")

    vbmeta_blob = data[vbmeta_off:vbmeta_off + vbmeta_size]
    payload_end = signer_off
    new_vbmeta_off = align(payload_end, 4096)

    if new_vbmeta_off + vbmeta_size > len(data) - AVB_FOOTER_SIZE:
        raise ValueError("Not enough room to relocate AVB metadata")

    out = bytearray(len(data))
    out[:payload_end] = data[:payload_end]
    out[new_vbmeta_off:new_vbmeta_off + vbmeta_size] = vbmeta_blob
    out[-AVB_FOOTER_SIZE:] = make_avb_footer(
        footer,
        original_size=payload_end,
        vbmeta_offset=new_vbmeta_off,
        vbmeta_size=vbmeta_size,
    )

    return bytes(out), {
        "type": image_type,
        "payload_end": payload_end,
        "signer_off": signer_off,
        "old_vbmeta_off": vbmeta_off,
        "new_vbmeta_off": new_vbmeta_off,
        "vbmeta_size": vbmeta_size,
        "avb_preserved": True,
        **signer_info(data, signer_off),
    }


def customize(data: bytes) -> tuple[bytes, dict]:
    image_type = detect_type(data)
    if image_type == "dtbo":
        return customize_dtbo(data)
    return customize_boot_or_vendor(data, image_type)


def default_output_name(src: Path, image_type: str) -> Path:
    if image_type == "dtbo":
        suffix = "_unsigned.img"
    else:
        suffix = "_custom.img"
    return src.with_name(src.stem + suffix)


def process_one(src: Path, dst: Path | None, overwrite: bool) -> Path:
    data = src.read_bytes()
    out, info = customize(data)

    if SIGNER_MAGIC in out:
        raise RuntimeError("Internal error: SignerVer02 still exists in output")

    if dst is None:
        dst = default_output_name(src, info["type"])

    if dst.exists() and not overwrite:
        raise FileExistsError(
            f"{dst} already exists. Use --overwrite or choose --output."
        )

    dst.write_bytes(out)

    print(f"\n[{src.name}]")
    print(f"  type          : {info['type']}")
    print(f"  input size    : {len(data)}")
    print(f"  SignerVer02   : 0x{info['signer_off']:x}")
    if info.get("version_name"):
        print(f"  version       : {info['version_name']}")
    if info.get("model_name"):
        print(f"  model         : {info['model_name']}")
    if info.get("system_rp"):
        print(f"  System RP     : {info['system_rp']}")
    if info.get("kernel_rp"):
        print(f"  Kernel RP     : {info['kernel_rp']}")
    print(f"  AVB preserved : {'yes' if info['avb_preserved'] else 'no'}")
    if info["avb_preserved"]:
        print(f"  AVB vbmeta    : 0x{info['old_vbmeta_off']:x} -> "
              f"0x{info['new_vbmeta_off']:x} ({info['vbmeta_size']} bytes)")
    print(f"  output        : {dst}")
    print(f"  SHA-256       : {sha256_bytes(out)}")

    return dst


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Convert tested Samsung boot/vendor_boot/dtbo stock images "
                    "into custom-binary style images by removing SignerVer02."
    )
    ap.add_argument("images", nargs="+", type=Path,
                    help="boot.img, vendor_boot.img and/or dtbo.img")
    ap.add_argument("-o", "--output", type=Path,
                    help="output path (only valid when one input is given)")
    ap.add_argument("--overwrite", action="store_true",
                    help="overwrite an existing output file")
    args = ap.parse_args()

    if args.output and len(args.images) != 1:
        ap.error("--output can only be used with one input image")

    try:
        for src in args.images:
            if not src.is_file():
                raise FileNotFoundError(src)
            process_one(src, args.output, args.overwrite)
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
