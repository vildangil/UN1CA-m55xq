#!/usr/bin/env python3
"""Prepare original UN1CA Odin firmware cache from an exact Bifrost Samsung ZIP.

No IMEI is sent or stored. Safe canonical paths only; ZIP CRC is verified by
streaming extraction. Creates the same .downloaded marker used by upstream
UN1CA's extract_fw.sh; it does not skip upstream extraction.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

EXPECTED = {
    "donor": {
        "model": "SM-S901E",
        "region": "TUR",
        "pda": "S901EXXSEGZH4",
        "firmware": "S901EXXSEGZH4/S901EOXMEGZH4/S901EXXSEGZH4",
    },
    "stock": {
        "model": "SM-M556B",
        "region": "INS",
        "pda": "M556BXXS4BYH2",
        "firmware": "M556BXXS4BYH2/M556BODM4BYH2/M556BXXS4BYH2/M556BXXS4BYH2",
    },
}
CHUNK = 4 * 1024 * 1024


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in EXPECTED:
        sys.exit("Usage: m55_prepare_odin_cache.py [donor|stock] samsung.zip out/odin")
    mode, archive, odin_root = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    info = EXPECTED[mode]
    destination = odin_root / (info["model"] + "_" + info["region"])
    destination.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(archive, "r", allowZip64=True) as zf:
        for entry in zf.infolist():
            base = Path(entry.filename).name
            if not (base.startswith(("AP_", "BL_", "CP_", "CSC_", "HOME_CSC_"))
                    and base.endswith(".tar.md5")):
                continue
            if "/" in entry.filename.strip("/") or "\\" in entry.filename:
                raise ValueError("Unexpected nested Samsung Odin entry " + entry.filename)
            if not re.match(r"^[A-Za-z0-9_.-]+$", base):
                raise ValueError("Unsafe Odin filename")
            if (base.startswith(("AP_", "BL_", "CP_")) and
                    not base.startswith(("AP_"+info["pda"]+"_",
                                        "BL_"+info["pda"]+"_",
                                        "CP_"+info["pda"]+"_"))):
                raise ValueError("Unexpected firmware PDA in " + base)
            if entry.file_size > 25 * 1024**3:
                raise ValueError("Unexpectedly large Odin tar")
            p = destination / base
            h = hashlib.sha256()
            with zf.open(entry) as src, p.open("wb") as dst:
                while data := src.read(CHUNK):
                    dst.write(data)
                    h.update(data)
            if p.stat().st_size != entry.file_size:
                raise ValueError("Truncated Odin tar: "+base)
            extracted.append({"file":base,"bytes":entry.file_size,"sha256":h.hexdigest()})
            print("M55_ODIN_CACHE_MEMBER",mode,base,entry.file_size,flush=True)
    if not any(x["file"].startswith("AP_"+info["pda"]+"_") for x in extracted):
        raise ValueError("Pinned AP tar not present")
    if not any(x["file"].startswith("BL_"+info["pda"]+"_") for x in extracted):
        raise ValueError("Pinned BL tar not present")
    (destination / ".downloaded").write_text(info["firmware"], encoding="utf-8")
    (destination / "m55-cache-manifest.json").write_text(json.dumps({
        "role":mode, "exact_firmware":info["firmware"],
        "no_imei_or_serial_used":True, "files":extracted
    },indent=2)+"\n",encoding="utf-8")
    print("M55_UNICA_ODIN_CACHE_READY",mode,info["firmware"],flush=True)


if __name__ == "__main__":
    main()
