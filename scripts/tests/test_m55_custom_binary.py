#!/usr/bin/env python3
"""Offline regression for the user's unchanged Samsung Custom Binary algorithm.

Actual M55 historical stock checksums are additionally checked by
m55_prepare_stock_kernel.py and in CI's stock_custom_images mode.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from m55.samsung_custom_binary import (  # noqa: E402
    SIGNER_MAGIC, align, customize, make_avb_footer, parse_avb_footer,
)

FOOTER = {
    "magic": b"AVBf", "major": 1, "minor": 0,
    "reserved": b"\0" * 28,
}


def test_boot(magic: bytes, kind: str):
    size = 64 * 1024
    orig_end = 0x2010 if kind == "boot" else 0x3000
    vbmeta_off = 0x5000
    vbmeta = b"AVB0" + b"\xAB" * 124
    src = bytearray(size)
    src[:len(magic)] = magic
    src[orig_end:orig_end + len(SIGNER_MAGIC)] = SIGNER_MAGIC
    src[vbmeta_off:vbmeta_off + len(vbmeta)] = vbmeta
    src[-64:] = make_avb_footer(FOOTER, orig_end + 0x100, vbmeta_off, len(vbmeta))
    output, info = customize(bytes(src))
    assert info["type"] == kind
    assert info["avb_preserved"]
    assert len(output) == len(src)
    assert SIGNER_MAGIC not in output
    new_footer = parse_avb_footer(output)
    assert new_footer is not None
    assert new_footer["original_size"] == orig_end
    assert new_footer["vbmeta_offset"] == align(orig_end, 4096)
    assert output[new_footer["vbmeta_offset"]:
                  new_footer["vbmeta_offset"] + len(vbmeta)] == vbmeta
    assert output[:orig_end] == src[:orig_end]
    assert src[orig_end:orig_end + len(SIGNER_MAGIC)] == SIGNER_MAGIC


def test_dtbo():
    size = 32768
    true_size = 0x2000
    original = bytearray(size)
    original[:8] = struct.pack(">II", 0xD7B7AB1E, true_size)
    original[8:true_size] = b"\x42" * (true_size - 8)
    original[true_size:true_size + len(SIGNER_MAGIC)] = SIGNER_MAGIC
    output, info = customize(bytes(original))
    assert info["type"] == "dtbo"
    assert len(output) == len(original)
    assert output[:true_size] == original[:true_size]
    assert output[true_size:] == b"\0" * (size - true_size)
    assert not info["avb_preserved"]


test_boot(b"ANDROID!", "boot")
test_boot(b"VNDRBOOT", "vendor_boot")
test_dtbo()
print("PASS: original Samsung Custom Binary boot/vendor_boot/dtbo regression")
