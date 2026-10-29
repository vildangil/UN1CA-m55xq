#!/usr/bin/env python3
"""Extract exact Samsung S22 One UI 8 donor EROFS SSI partitions.

Stream AP tar from Samsung Odin ZIP, decompress sparse super on the fly,
and write only the required logical images. Never flash or sign anything.
"""
from __future__ import annotations
import hashlib
import json
import re
import struct
import sys
import tarfile
import zipfile
from pathlib import Path
import lz4.frame
from m55_extract_dynamic import metadata_extents, extract_sparse, exact_read

PREFIX_BYTES = 16 * 1024 * 1024
PARTS = ("system", "product", "system_ext")
EXPECTED = "S901EXXSEGZH4"


def raw_head(stream, maximum=PREFIX_BYTES):
    header = exact_read(stream, 28)
    (magic, major, minor, header_size, chunk_header,
     block_size, total_blocks, total_chunks, checksum) = struct.unpack("<I4H4I", header)
    if magic != 0xED26FF3A or major != 1 or header_size < 28 or chunk_header < 12:
        raise ValueError("Donor super not a valid sparse image")
    if header_size > 28:
        exact_read(stream, header_size - 28)
    head = bytearray()
    for _ in range(total_chunks):
        if len(head) >= maximum:
            break
        ch = exact_read(stream, chunk_header)
        kind, _, count, total = struct.unpack_from("<HHII", ch)
        logical = count * block_size
        allowed = min(maximum - len(head), logical)
        if kind == 0xCAC1:
            if total != chunk_header + logical:
                raise ValueError("Bad sparse RAW chunk")
            head += exact_read(stream, allowed)
            if allowed < logical:
                break
        elif kind == 0xCAC2:
            if total != chunk_header + 4:
                raise ValueError("Bad FILL chunk")
            pat = exact_read(stream, 4)
            head += (pat * ((allowed + 3) // 4))[:allowed]
        elif kind == 0xCAC3:
            if total != chunk_header:
                raise ValueError("Bad DONT_CARE chunk")
            head += b"\0" * allowed
        elif kind == 0xCAC4:
            if total != chunk_header + 4:
                raise ValueError("Bad CRC chunk")
            exact_read(stream, 4)
        else:
            raise ValueError(f"Unknown sparse chunk {kind:#x}")
    return bytes(head)


def donor_super(z, ap):
    with z.open(ap) as inp, tarfile.open(fileobj=inp, mode="r|") as t:
        for member in t:
            if member.isfile() and member.name.rstrip("/").split("/")[-1] in ("super.img.lz4", "super.img"):
                if member.name.endswith(".lz4"):
                    with t.extractfile(member) as file:
                        with lz4.frame.open(file, "rb") as data:
                            yield data
                else:
                    with t.extractfile(member) as file:
                        yield file
                return
    raise ValueError("S22 donor super missing in AP archive")


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def main():
    inp, out, reportdir = map(Path, sys.argv[1:4])
    out.mkdir(parents=True, exist_ok=True)
    reportdir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(inp) as z:
        ap_list = [f for f in z.namelist()
                   if re.search(r"(?:^|/)AP_" + EXPECTED + r"_[^/]+\.tar\.md5$", f)]
        if len(ap_list) != 1:
            raise ValueError("Donor archive has no exact pinned S901E AP")
        ap = ap_list[0]
        print("M55_DONOR_AP_VERIFIED", ap, flush=True)
        stream = donor_super(z, ap)
        head = raw_head(next(stream))
        # Close nested tar/lz4 streams deterministically by exhausting generator.
        stream.close()
        wanted = set(PARTS)
        # S22 source may have system_ext nested in system partition instead.
        layout = metadata_extents(head, {"system", "product"})
        if "system_ext" in head.decode("latin1", "ignore"):
            try:
                layout = metadata_extents(head, wanted)
            except ValueError:
                pass
        print("M55_DONOR_LAYOUT", {k:v["length"] for k,v in layout.items()}, flush=True)
        stream = donor_super(z, ap)
        extract_sparse(next(stream), layout, out)
        stream.close()

    report = {"model":"SM-S901E", "region":"TUR", "pda":EXPECTED,
              "role":"One UI 8 / Android 16 donor, NOT hardware boot chain",
              "partitions":{}, "warnings":[]}
    for name, data in layout.items():
        f = out / (name + ".img")
        with f.open("rb") as fd:
            fd.seek(1024)
            magic = fd.read(4).hex()
        if magic != "e2e1f5e0":
            raise ValueError(f"Donor {name} has unexpected FS magic {magic}")
        report["partitions"][name] = {
            "bytes":f.stat().st_size, "sha256":sha256(f),
            "filesystem":"erofs", "extents":len(data["regions"])
        }
        print("M55_DONOR_PARTITION_OK",name,f.stat().st_size, flush=True)
    (reportdir / "donor_partitions.json").write_text(json.dumps(report,indent=2)+"\n")
    print("M55_DONOR_EXTRACT_COMPLETE",flush=True)


if __name__ == "__main__":
    main()
