#!/usr/bin/env python3
"""Extract M55 vendor/odm/vendor_dlkm directly from a Samsung sparse super stream.

Based on AOSP liblp metadata_format.h and Android sparse-image format.
Does not write an intermediate full-sized 13.6GB raw super image.
"""
import contextlib
import hashlib
import json
import os
import struct
import sys
import tarfile
import zipfile
from pathlib import Path

import lz4.frame

TARGETS = ("vendor", "odm", "vendor_dlkm")
IO_CHUNK = 2 * 1024 * 1024


def exact_read(stream, count):
    chunks = []
    while count:
        chunk = stream.read(min(count, IO_CHUNK))
        if not chunk:
            raise ValueError("Truncated Samsung super image")
        chunks.append(chunk)
        count -= len(chunk)
    return b"".join(chunks)


def u32(blob, offset):
    return struct.unpack_from("<I", blob, offset)[0]


def metadata_extents(blob, requested=None):
    requested = set(requested if requested is not None else TARGETS)
    geometry_offset = next((x for x in (4096, 8192)
                            if u32(blob, x) == 0x616c4467), None)
    if geometry_offset is None:
        raise ValueError("No valid liblp geometry")
    metadata_max, slots, block_size = struct.unpack_from("<III", blob,
                                                          geometry_offset + 40)
    if not (0 < metadata_max <= 1048576 and slots > 0 and block_size in (512, 4096)):
        raise ValueError("Invalid liblp geometry fields")
    off = 12288
    if u32(blob, off) != 0x414C5030:
        raise ValueError("Invalid liblp primary metadata header")
    header_size = u32(blob, off + 8)
    table_size = u32(blob, off + 44)
    if not (128 <= header_size <= 4096 and 0 < table_size <= metadata_max):
        raise ValueError("Invalid liblp table lengths")
    data_at = off + header_size
    descriptors = [struct.unpack_from("<III", blob, off + 80 + n * 12)
                   for n in range(4)]
    records = []
    for name, (start, count, row_size) in zip(
            ("partitions", "extents", "groups", "block_devices"), descriptors):
        if count > 4096 or row_size > 256 or start + count * row_size > table_size:
            raise ValueError("Invalid " + name + " table bounds")
        records.append([blob[data_at + start + i * row_size:
                             data_at + start + (i + 1) * row_size]
                        for i in range(count)])
    parts, extents, _, devices = records
    if len(devices) != 1:
        raise ValueError("Multidevice super not supported")
    layout = {}
    for part in parts:
        label = part[:36].split(b"\0")[0].decode("ascii", "replace")
        if label not in requested:
            continue
        _, first, count, _ = struct.unpack_from("<IIII", part, 36)
        if first + count > len(extents):
            raise ValueError("Invalid extent indices for " + label)
        regions = []
        logical_offset = 0
        for extent in extents[first:first + count]:
            num_sectors, kind, sector, source = struct.unpack_from("<QIQI", extent)
            byte_count = num_sectors * 512
            if kind not in (0, 1) or (kind == 0 and source != 0):
                raise ValueError("Unexpected liblp target for " + label)
            if kind == 0:
                regions.append({"start": sector * 512,
                                "end": sector * 512 + byte_count,
                                "offset": logical_offset})
            logical_offset += byte_count
        layout[label] = {"length": logical_offset, "regions": regions}
    if not requested.issubset(layout):
        raise ValueError("Requested LP partitions absent: " + str(requested - layout.keys()))
    return layout


def copy_intersections(offset, payload, layout, handles):
    end = offset + len(payload)
    for label, meta in layout.items():
        fd = handles[label]
        for region in meta["regions"]:
            start = max(offset, region["start"])
            stop = min(end, region["end"])
            if start >= stop:
                continue
            fd.seek(region["offset"] + start - region["start"])
            fd.write(payload[start - offset:stop - offset])


def write_fill(start, length, pattern, layout, handles):
    end = start + length
    for label, meta in layout.items():
        for region in meta["regions"]:
            pos = max(start, region["start"])
            stop = min(end, region["end"])
            if pos >= stop:
                continue
            fd = handles[label]
            fd.seek(region["offset"] + pos - region["start"])
            # FILL pattern repeats relative to sparse chunk start.
            while pos < stop:
                take = min(stop - pos, IO_CHUNK)
                rel = (pos - start) % len(pattern)
                buf = (pattern[rel:] + pattern * ((take // len(pattern)) + 1))[:take]
                fd.write(buf)
                pos += take


def extract_sparse(stream, layout, raw_dir):
    files = {}
    try:
        for label, meta in layout.items():
            file_path = raw_dir / (label + ".img")
            fd = file_path.open("wb+")
            fd.truncate(meta["length"])
            files[label] = fd
        header = exact_read(stream, 28)
        magic, major, minor, file_header, chunk_header, block_sz, total_blocks, total_chunks, checksum = struct.unpack("<I4H4I", header)
        if (magic, major) != (0xED26FF3A, 1) or not (512 <= block_sz <= 1048576):
            raise ValueError("Not an Android sparse super image")
        if file_header < 28 or chunk_header < 12 or chunk_header > 4096:
            raise ValueError("Invalid Android sparse header")
        if file_header > 28:
            exact_read(stream, file_header - 28)
        position = 0
        for i in range(total_chunks):
            ch = exact_read(stream, chunk_header)
            kind, _, blocks, total_size = struct.unpack_from("<HHII", ch)
            amount = blocks * block_sz
            payload_size = total_size - chunk_header
            if kind == 0xCAC1:
                if amount != payload_size:
                    raise ValueError("Sparse RAW chunk size mismatch")
                remaining = amount
                while remaining:
                    data = exact_read(stream, min(remaining, IO_CHUNK))
                    copy_intersections(position, data, layout, files)
                    position += len(data)
                    remaining -= len(data)
            elif kind == 0xCAC2:
                if payload_size != 4:
                    raise ValueError("Sparse FILL size mismatch")
                pattern = exact_read(stream, 4)
                write_fill(position, amount, pattern, layout, files)
                position += amount
            elif kind == 0xCAC3:
                if payload_size != 0:
                    raise ValueError("Sparse DONT_CARE size mismatch")
                position += amount
            elif kind == 0xCAC4:
                if payload_size != 4:
                    raise ValueError("Sparse CRC32 size mismatch")
                exact_read(stream, 4)
            else:
                raise ValueError("Unknown Android sparse chunk type")
            if i % 30 == 0:
                print("M55_SUPER_CHUNK", i, "/", total_chunks, flush=True)
        if position != total_blocks * block_sz:
            raise ValueError("Sparse output logical length mismatch")
    finally:
        for fd in files.values():
            fd.close()


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as fd:
        for data in iter(lambda: fd.read(4 * 1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def main():
    source = Path(sys.argv[1])
    metadata_head = Path(sys.argv[2])
    raw_dir = Path(sys.argv[3])
    report_dir = Path(sys.argv[4])
    raw_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    layout = metadata_extents(metadata_head.read_bytes())
    print("M55_LP_TARGETS", {k:v["length"] for k,v in layout.items()}, flush=True)
    with zipfile.ZipFile(source) as archive:
        members = [f for f in archive.namelist()
                   if f.startswith("AP_M556BXXS4BYH2_") and f.endswith(".tar.md5")]
        if len(members) != 1:
            raise ValueError("Wrong M55 stock AP archive")
        with archive.open(members[0]) as ap, tarfile.open(fileobj=ap, mode="r|") as tar:
            found = False
            for entry in tar:
                if Path(entry.name).name != "super.img.lz4":
                    continue
                found = True
                with tar.extractfile(entry) as source:
                    with lz4.frame.open(source, "rb") as data:
                        extract_sparse(data, layout, raw_dir)
                break
            if not found:
                raise ValueError("No super.img.lz4 in M55 stock AP")
    result = {}
    for name in layout:
        path = raw_dir / (name + ".img")
        with path.open("rb") as fd:
            fd.seek(1024)
            magic = fd.read(4).hex()
        result[name] = {"bytes":path.stat().st_size,
                        "sha256":digest(path),
                        "erofs_magic":magic == "e2e1f5e0",
                        "magic_at_1024":magic,
                        "extent_count":len(layout[name]["regions"])}
        print("M55_LP_EXTRACT", name, result[name], flush=True)
    (report_dir / "dynamic_partition_images.json").write_text(
        json.dumps(result,indent=2),encoding="utf-8")
    print("M55_DYNAMIC_EXTRACTION_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
