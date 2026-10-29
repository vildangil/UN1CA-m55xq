#!/usr/bin/env python3
"""Inspect M55 Samsung Odin ZIP, its AP tar, super LP metadata and AVB images.

Never flash, mount or publish user partitions. Stream super.img.lz4: only
the early metadata area is decompressed (no multi-gigabyte raw super copy).
"""
import hashlib
import io
import json
import os
import re
import struct
import sys
import tarfile
import zipfile
from pathlib import Path
import lz4.frame

SOURCE = Path(sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
MAX_IMAGE_BYTES = 160 * 1024 * 1024
REPORT = {"model": "SM-M556B", "base_pda": "M556BXXS4BYH2",
          "source_bytes": SOURCE.stat().st_size, "ap_entries": [], "partitions": [],
          "small_images": [], "warnings": [], "lp_metadata": {}}
wanted = re.compile(r"^(boot|vendor_boot|init_boot|dtbo|vbmeta(?:_system|_vendor)?|recovery)(?:\.img)(?:\.lz4)?$")
super_name = re.compile(r"^super(?:\.img)?(?:\.lz4)?$")


def sha256_file(path):
    dig = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(4 * 1024 * 1024), b""):
            dig.update(part)
    return dig.hexdigest()


def small_file(tar, entry):
    source = tar.extractfile(entry)
    if source is None:
        return
    name = Path(entry.name).name
    bare = name.removesuffix(".lz4")
    dest = OUT / bare
    if entry.size > MAX_IMAGE_BYTES:
        REPORT["warnings"].append(name + " skipped: too large")
        return
    reader = lz4.frame.open(source, "rb") if name.endswith(".lz4") else source
    with reader, dest.open("wb") as sink:
        size = 0
        while True:
            chunk = reader.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_IMAGE_BYTES:
                sink.close()
                dest.unlink(missing_ok=True)
                REPORT["warnings"].append(bare + " expanded too large")
                return
            sink.write(chunk)
    with dest.open("rb") as f:
        magic = f.read(8).hex()
    info = {"file": bare, "bytes": size, "sha256": sha256_file(dest),
            "magic": magic}
    if bare.startswith("vbmeta"):
        with dest.open("rb") as f:
            info["avb_magic_valid"] = f.read(4) == b"AVB0"
    REPORT["small_images"].append(info)
    print("M55_STOCK_IMAGE", bare, "size", size, "sha256", info["sha256"], flush=True)


def extract_head(raw, maximum=16 * 1024 * 1024):
    """Read beginning of a normal or Android sparse super image."""
    magic = raw.read(4)
    if len(magic) < 4:
        raise ValueError("Empty super image")
    if magic != b"\x3a\xff\x26\xed":
        return magic + raw.read(maximum - 4), {"type": "raw"}
    rest = raw.read(24)
    if len(rest) < 24:
        raise ValueError("Truncated Android sparse header")
    _, major, minor, file_hdr, chunk_hdr, blk_size, blocks, chunks, checksum = struct.unpack(
        "<I4H4I", magic + rest
    )
    if major != 1 or blk_size < 512 or blk_size > 1024 * 1024:
        raise ValueError("Invalid Android sparse header")
    if file_hdr > 28:
        raw.read(file_hdr - 28)
    buf = bytearray()
    for _ in range(chunks):
        if len(buf) >= maximum:
            break
        ch = raw.read(chunk_hdr)
        if len(ch) < chunk_hdr:
            raise ValueError("Truncated sparse chunk header")
        kind, _, block_count, total_size = struct.unpack_from("<HHII", ch)
        logical = block_count * blk_size
        data_size = total_size - chunk_hdr
        n = min(logical, maximum - len(buf))
        if kind == 0xCAC1:  # RAW
            if data_size != logical:
                raise ValueError("Unexpected RAW sparse chunk length")
            buf.extend(raw.read(n))
            if n < data_size:
                break
        elif kind == 0xCAC2:  # FILL
            value = raw.read(4)
            if len(value) != 4:
                raise ValueError("Truncated FILL sparse chunk")
            buf.extend((value * ((n + 3) // 4))[:n])
        elif kind == 0xCAC3:  # DON'T CARE
            buf.extend(b"\0" * n)
        elif kind == 0xCAC4:  # CRC32
            raw.read(4)
        else:
            raise ValueError(f"Unknown sparse chunk kind {kind:#x}")
    return bytes(buf), {"type": "android_sparse", "block_size": blk_size,
                         "block_count": blocks, "raw_super_bytes": blk_size * blocks,
                         "sparse_chunks": chunks}


def lp_tables(blob):
    geom = None
    for off in (4096, 8192):
        if len(blob) >= off + 52 and struct.unpack_from("<I", blob, off)[0] == 0x616c4467:
            magic, size = struct.unpack_from("<II", blob, off)
            metadata_max, slots, sector_size = struct.unpack_from("<III", blob, off + 40)
            geom = {"metadata_max_size": metadata_max,
                    "metadata_slot_count": slots, "logical_block_size": sector_size}
            break
    if not geom:
        raise ValueError("LP geometry not found in first 16 MiB of super")
    found = None
    for off in [12288, 12288 + geom["metadata_max_size"], 4096 + 8192]:
        if len(blob) < off + 132:
            continue
        if struct.unpack_from("<I", blob, off)[0] == 0x414C5030:
            found = off
            break
    if found is None:
        # Fallback: sparse super produced by alternate lpmake layout.
        for off in range(12288, min(len(blob) - 132, 8 * 1024 * 1024), 4096):
            if struct.unpack_from("<I", blob, off)[0] == 0x414C5030:
                found = off
                break
    if found is None:
        raise ValueError("LP metadata header not found")
    major, minor, hdr_size = struct.unpack_from("<HHI", blob, found + 4)
    tables_size = struct.unpack_from("<I", blob, found + 44)[0]
    if hdr_size < 128 or hdr_size > 4096 or tables_size > 16 * 1024 * 1024:
        raise ValueError("LP metadata size invalid")
    tables = found + hdr_size
    descriptors = [struct.unpack_from("<III", blob, found + 80 + i * 12)
                   for i in range(4)]
    out = {"geometry": geom, "metadata_header_offset": found,
           "major": major, "minor": minor, "header_size": hdr_size,
           "tables_size": tables_size}
    labels = ("partitions", "extents", "groups", "block_devices")
    data = {}
    for label, (offset, count, size) in zip(labels, descriptors):
        if count > 1024 or size > 1024 or offset + count * size > tables_size:
            raise ValueError("LP table descriptor invalid: " + label)
        data[label] = [blob[tables + offset + i * size:
                             tables + offset + (i + 1) * size]
                       for i in range(count)]
        if any(len(x) != size for x in data[label]):
            raise ValueError("LP table truncated: " + label)
    groups = []
    for row in data["groups"]:
        name = row[:36].split(b"\0")[0].decode("ascii", "replace")
        max_bytes = struct.unpack_from("<Q", row, 40)[0] if len(row) >= 48 else 0
        groups.append({"name": name, "maximum_size": max_bytes})
    devices = []
    for row in data["block_devices"]:
        if len(row) < 64:
            continue
        first_sector, alignment, offset, size = struct.unpack_from("<QIIQ", row, 0)
        name = row[24:60].split(b"\0")[0].decode("ascii", "replace")
        devices.append({"name": name, "size": size, "first_sector": first_sector,
                        "alignment": alignment, "alignment_offset": offset})
    partitions = []
    for row in data["partitions"]:
        if len(row) < 52:
            continue
        name = row[:36].split(b"\0")[0].decode("ascii", "replace")
        attributes, first_extent, extent_count, group_idx = struct.unpack_from("<IIII", row, 36)
        ext_sectors = 0
        for e in data["extents"][first_extent:first_extent + extent_count]:
            if len(e) >= 8:
                ext_sectors += struct.unpack_from("<Q", e)[0]
        partitions.append({"name": name, "bytes": ext_sectors * 512,
                           "attributes": attributes, "num_extents": extent_count,
                           "group": groups[group_idx]["name"] if group_idx < len(groups)
                           else str(group_idx)})
    out["groups"] = groups
    out["block_devices"] = devices
    out["partitions"] = partitions
    return out


def inspect_super(tar, entry):
    source = tar.extractfile(entry)
    if source is None:
        return
    if entry.name.endswith(".lz4"):
        decoder = lz4.frame.open(source, "rb")
    else:
        decoder = source
    with decoder:
        head, sparse_info = extract_head(decoder)
    (OUT / "super_first16MiB.raw").write_bytes(head)
    info = {"source_tar_entry": entry.name, "tar_bytes": entry.size,
            "head_bytes": len(head), **sparse_info}
    try:
        info.update(lp_tables(head))
    except Exception as exc:
        REPORT["warnings"].append("LP metadata parsing: " + str(exc))
    REPORT["lp_metadata"] = info
    REPORT["partitions"] = info.get("partitions", [])
    print("M55_STOCK_SUPER", "type", sparse_info["type"],
          "partitions", len(REPORT["partitions"]), flush=True)
    for p in REPORT["partitions"]:
        print("M55_STOCK_LP", p["name"], p["bytes"], p["group"], flush=True)


with zipfile.ZipFile(SOURCE) as z:
    bad = z.testzip()
    if bad:
        raise ValueError("Bad CRC in ZIP member: " + bad)
    REPORT["zip_members"] = [{"name": x.filename, "bytes": x.file_size}
                             for x in z.infolist()]
    ap = [x for x in z.infolist() if re.search(r"(?:^|/)AP_M556BXXS4BYH2_[^/]*\.tar\.md5$", x.filename)]
    if len(ap) != 1:
        raise ValueError(f"Expected one exact M55 BYH2 AP tar, found {len(ap)}")
    with z.open(ap[0]) as inp, tarfile.open(fileobj=inp, mode="r|") as archive:
        for e in archive:
            if not e.isfile():
                continue
            name = Path(e.name).name
            REPORT["ap_entries"].append({"name": name, "bytes": e.size})
            if wanted.match(name):
                small_file(archive, e)
            elif super_name.match(name):
                inspect_super(archive, e)
            else:
                print("M55_STOCK_AP_ENTRY", name, e.size, flush=True)

(OUT / "report.json").write_text(json.dumps(REPORT, indent=2), encoding="utf-8")
lines = [f"Model: {REPORT['model']}", f"Firmware: {REPORT['base_pda']}",
         f"AP entries: {len(REPORT['ap_entries'])}",
         f"LP partitions: {len(REPORT['partitions'])}", ""]
for p in REPORT["partitions"]:
    lines.append(f"{p['name']}: {p['bytes']} bytes, group={p['group']}")
lines += ["", "Small image checksums:"]
for p in REPORT["small_images"]:
    lines.append(f"{p['file']}: {p['bytes']} bytes SHA256={p['sha256']}")
lines += ["", "Warnings:"] + REPORT["warnings"]
(OUT / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("M55_STOCK_ANALYSIS_COMPLETE", flush=True)
