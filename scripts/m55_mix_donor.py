#!/usr/bin/env python3
"""Gate a provisional S22 One UI 8 + M55 One UI 7 dynamic partition mix.

Produces metadata, checksums and a lpmake command; never signs or flashes.
Do not mistake EROFS/size success for VINTF or AVB compatibility.
"""
import hashlib
import json
import os
import shlex
import sys
from pathlib import Path

SUPER_SIZE = 13631488000
GROUP_SIZE = 13627293696
STOCK = {
    "vendor": (2008227840, "825c78c6855e837b07d65e6e30d30959ef2caab43bf7eaeb12a305d0f8a34203"),
    "odm": (1699840, "a6520727edcb70a1119368538d9ba566f571d71b300963ffcf819947db075f82"),
    "vendor_dlkm": (126201856, "e52e39b4b5443d398528c21a483757c3af673a29d39ba46bd086d17361d92ae4"),
}

def digest(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(blk)
    return h.hexdigest()

def check_image(p, expected=None):
    if not p.is_file():
        raise RuntimeError("Missing image: "+str(p))
    size=p.stat().st_size
    if size <= 0 or size%4096:
        raise RuntimeError("Non-aligned or empty image: "+str(p))
    with p.open("rb") as f:
        f.seek(1024)
        if f.read(4) != b"\xe2\xe1\xf5\xe0":
            raise RuntimeError("Not EROFS: "+str(p))
    sha = digest(p)
    if expected and (size,sha)!=expected:
        raise RuntimeError("Modified or incorrect Samsung M55 image: "+str(p))
    return {"bytes":size,"sha256":sha,"fs":"erofs"}

def main():
    donor, stock, reports, output=map(Path,sys.argv[1:5])
    output.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((reports/"donor_partitions.json").read_text())
    if metadata.get("pda")!="S901EXXSEGZH4" or metadata.get("model")!="SM-S901E":
        raise RuntimeError("Wrong S22 donor")
    mixed={}
    for name in ("system","product"):
        p=donor/(name+".img")
        v=check_image(p)
        if metadata["partitions"][name]["sha256"]!=v["sha256"]:
            raise RuntimeError("Donor manifest hash mismatch: "+name)
        mixed[name]={"origin":"S22 One UI8",**v}
    systemext=donor/"system_ext.img"
    if systemext.is_file():
        mixed["system_ext"]={"origin":"S22 One UI8",**check_image(systemext)}
    else:
        # M55 uses system_ext as dynamic partition. Do not silently supply
        # an Android 15 system_ext with Android 16 system/product.
        raise RuntimeError("S22 donor does not have separate system_ext: manual merge needed")
    for name, expected in STOCK.items():
        mixed[name]={"origin":"M55 One UI7",**check_image(stock/(name+".img"), expected)}
    total=sum(x["bytes"] for x in mixed.values())
    manifest={"model":"SM-M556B","donor_pda":"S901EXXSEGZH4",
              "target_pda":"M556BXXS4BYH2","super_size":SUPER_SIZE,
              "super_group_size":GROUP_SIZE,"partitions":mixed,
              "sum_logical_bytes":total,"unused_group_bytes":GROUP_SIZE-total,
              "stage":"PRELIMINARY_PARTITION_MIX_NOT_BOOT_VERIFIED_NOT_FLASHABLE",
              "blocking_checks":[
                "Samsung SEC feature configuration has not been ported",
                "S22 system/product ABI, VINTF and M55 vendor HAL compatibility unverified",
                "Kernel-module ABI and user-provided patched kernel not integrated",
                "AVB signing/rollback index chain cannot be assumed valid",
                "No device boot or DSU boot test performed",
              ]}
    if total>GROUP_SIZE:raise RuntimeError(f"Insufficient M55 super space: need={total} max={GROUP_SIZE} over={total-GROUP_SIZE}")
    images={**{k:donor/(k+".img") for k in ("system","product","system_ext")},
            **{k:stock/(k+".img") for k in STOCK}}
    args=["lpmake","--metadata-size","65536","--super-name","super",
          "--metadata-slots","2","--device",f"super:{SUPER_SIZE}",
          "--group",f"qti_dynamic_partitions:{GROUP_SIZE}","--sparse"]
    for name in mixed:
        args += ["--partition", f"{name}:readonly:{mixed[name]['bytes']}:qti_dynamic_partitions",
                 "--image",f"{name}={images[name]}"]
    args += ["--output","out/M55-ONEUI8-CANDIDATE-UNVERIFIED-super.img"]
    # Do not execute the potentially dangerous build implicitly. This is a
    # reproducible sizing/audit recipe, not an installable image.
    (output/"lpmake_candidate_preview.sh").write_text("#!/bin/sh\n# NON-FLASHABLE / NEVER DEPLOY WITHOUT DEVICE-SPECIFIC TESTS\n"+shlex.join(args)+"\n")
    (output/"candidate_partition_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (output/"DO_NOT_FLASH.txt").write_text(
        "PRELIMINARY MIX: S22 One UI 8 + M55 Android 15 vendor. NOT BOOT-TESTED.\n"
        "Build checks passed only for source identity, EROFS and super sizing.\n"
        "The candidate lpmake command is NOT executed by this validation.\n"
        "Do not flash a generated super or stock vbmeta to the M55.\n"
    )
    print("M55_DONOR_MIX_PRECHECK_OK bytes",total,"headroom",GROUP_SIZE-total,flush=True)

if __name__=="__main__":main()
