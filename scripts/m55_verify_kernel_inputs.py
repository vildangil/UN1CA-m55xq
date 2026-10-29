#!/usr/bin/env python3
"""Verify exactly the patched kernel images already tested by the M55 owner.

This prevents using stock BL images or mismatched kernels/modules in UN1CA CI.
No images are created or signed.
"""
import hashlib
import sys
from pathlib import Path

EXPECTED = {
    "boot.img": ("937a4c973ff7daff7fcc63c6244526be9b11a69b4a7d2729c39661fd9ccf4479", 100663296),
    "vendor_boot.img": ("dd0ac56f3d186ce0545f47352ce2db4ff09221c7654bf7236f9c1a1bae5c719c", 100663296),
    "dtbo.img": ("b83bb40ac00a9e4e4855a6c47527326a17b681fb5af840153ea69726e2898b2b", 8388608),
    "vendor_dlkm.img": ("1fa2a5f271b7f3ac4b9c61631065472015ca507821281dbbaa3f2519d037e37c", 56664064),
}


def main():
    folder = Path(sys.argv[1])
    for name, (digest, size) in EXPECTED.items():
        file = folder / name
        if not file.is_file() or file.stat().st_size != size:
            raise SystemExit(f"M55_KERNEL_INPUT_INVALID_SIZE {name}: expected {size}")
        h = hashlib.sha256()
        with file.open("rb") as inp:
            while block := inp.read(4 * 1024 * 1024):
                h.update(block)
        if h.hexdigest() != digest:
            raise SystemExit(f"M55_KERNEL_INPUT_SHA256_MISMATCH {name}")
        print(f"M55_PATCHED_KERNEL_VERIFIED {name} {size} {digest}",flush=True)
    print("M55_KERNEL_PAIRING_VERIFIED",flush=True)


if __name__ == "__main__":
    main()
