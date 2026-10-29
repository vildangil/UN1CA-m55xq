#!/usr/bin/env python3
"""Read-only UN1CA M55 audit of extracted One UI 7 stock images."""
import hashlib
import json
import os
import re
import struct
import sys
from pathlib import Path

raw = Path(sys.argv[1])
extracted = Path(sys.argv[2])
output = Path(sys.argv[3])
stock_small = Path(sys.argv[4])
output.mkdir(parents=True, exist_ok=True)

WHITELIST = re.compile(
    r"(^|/)(build\.prop|fstab[^/]*|ueventd[^/]*\.rc|modules\.(?:load|dep|alias|softdep)|"
    r"manifest[^/]*\.xml|compatibility_matrix[^/]*\.xml)$|"
    r"(^|/)etc/(?:init|vintf)/.*\.(?:xml|rc)$|"
    r"(^|/)etc/selinux/[^/]*\.(?:cil|txt|contexts)$")
MAX_CONFIG = 1024 * 1024


def hash_file(p):
    h = hashlib.sha256()
    with p.open("rb") as fd:
        for part in iter(lambda: fd.read(4 * 1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def avb_info(path):
    blob = path.read_bytes()
    if len(blob) < 256 or blob[:4] != b"AVB0":
        raise ValueError("Invalid AVB header: " + path.name)
    U32 = lambda off: struct.unpack_from(">I", blob, off)[0]
    U64 = lambda off: struct.unpack_from(">Q", blob, off)[0]
    auth = U64(12)
    aux = U64(20)
    desc_offset, desc_size = U64(96), U64(104)
    start = 256 + auth + desc_offset
    end = start + desc_size
    if end > len(blob) or end > 256 + auth + aux:
        raise ValueError("AVB descriptors outside signed vbmeta")
    res = {"file":path.name,"sha256":hash_file(path),
           "required_version":[U32(4),U32(8)],
           "algorithm_type":U32(28),"rollback_index":U64(112),
           "flags":U32(120),"rollback_index_location":U32(124),
           "descriptors":[]}
    while start < end:
        if start + 16 > end:
            raise ValueError("Truncated AVB descriptor header")
        tag, length = struct.unpack_from(">QQ", blob, start)
        start += 16
        if start + length > end or length > 200000:
            raise ValueError("Malformed AVB descriptor")
        body = blob[start:start+length]
        item = {"tag": tag, "size": length}
        if tag == 2 and len(body) >= 116:
            image_size = struct.unpack_from(">Q",body,0)[0]
            alg = body[8:40].split(b"\0")[0].decode("ascii", "replace")
            name_len,salt_len,digest_len,flags = struct.unpack_from(">IIII",body,40)
            if 116 + name_len + salt_len + digest_len <= len(body):
                name = body[116:116+name_len].decode("ascii", "replace")
                item.update({"type":"hash","partition":name,"image_size":image_size,
                             "algorithm":alg,"flags":flags})
        if tag == 1 and len(body) >= 164:
            # AvbHashtreeDescriptor has a fixed 164-byte header.
            image_size = struct.unpack_from(">Q",body,4)[0]
            item.update({"type":"hashtree","image_size":image_size})
        if tag == 4:
            item.update({"type":"chain"})
        if tag == 0:
            item.update({"type":"property"})
        res["descriptors"].append(item)
        start += length
    return res


avb = [avb_info(p) for p in (stock_small / "vbmeta.img",
                              stock_small / "vbmeta_system.img")]
(output / "avb_report.json").write_text(json.dumps(avb,indent=2),encoding="utf-8")
print("M55_AVB",[(x["file"],x["algorithm_type"],x["flags"],
                 len(x["descriptors"])) for x in avb], flush=True)

partition_report = {}
snippets = output / "stock_configs"
snippets.mkdir(exist_ok=True)
for partition in ("vendor", "odm", "vendor_dlkm"):
    root = extracted / partition
    if not root.is_dir():
        raise ValueError("Missing extracted filesystem: " + partition)
    image = raw / (partition + ".img")
    if not image.is_file():
        raise ValueError("Missing LP image: " + partition)
    files = []
    total = 0
    names = []
    for directory, dirs, filenames in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
        for name in filenames:
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            size = path.stat().st_size
            files.append({"path":relative,"size":size})
            total += size
            if WHITELIST.search(relative) and size <= MAX_CONFIG:
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if "\0" in content:
                    continue
                destination = snippets / partition / relative
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_text(content,encoding="utf-8")
                names.append(relative)
    files.sort(key=lambda x:x["path"])
    (output / (partition + "_files.json")).write_text(
        json.dumps(files,indent=1), encoding="utf-8")
    names.sort()
    props = {}
    build_prop = root / "build.prop"
    if build_prop.is_file():
        for line in build_prop.read_text(errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k,v = line.split("=",1)
                if k.startswith(("ro.product.","ro.vendor.","ro.build.","ro.board.","ro.hardware.")):
                    props[k] = v
    partition_report[partition] = {
        "image_bytes":image.stat().st_size,"image_sha256":hash_file(image),
        "files":len(files),"file_bytes":total,
        "interesting_configs":names,
        "hardware_interfaces":[f["path"] for f in files
                               if ("/hw/" in f["path"] and f["path"].endswith(".so"))],
        "kernel_modules":[f["path"] for f in files if f["path"].endswith(".ko")],
        "properties":props,
    }
    print("M55_VENDOR_AUDIT",partition,"files",len(files),
          "configs",len(names),"modules",
          len(partition_report[partition]["kernel_modules"]),flush=True)

(output / "vendor_odm_report.json").write_text(
    json.dumps(partition_report,indent=2),encoding="utf-8")
summary = ["# M55 stock One UI 7 vendor and ODM inspection",
           "Firmware: M556BXXS4BYH2 (Android 15).",
           "All extracted data originated from Samsung FUS. Do NOT flash these images.",
           "",
           "## AVB"]
for v in avb:
    summary += [f"- {v['file']}: flags={v['flags']}, algorithm_type={v['algorithm_type']}, "
                f"rollback_location={v['rollback_index_location']}, descriptors={len(v['descriptors'])}"]
    for desc in v["descriptors"]:
        if desc.get("type") == "hash":
            summary += [f"  - Hash descriptor: {desc['partition']} "
                        f"({desc['image_size']} bytes; {desc['algorithm']})"]
summary += ["", "## Partitions"]
for name, report in partition_report.items():
    summary += [f"- {name}: image bytes {report['image_bytes']}, "
                f"files {report['files']}, HAL libraries "
                f"{len(report['hardware_interfaces'])}, "
                f"kernel modules {len(report['kernel_modules'])}"]
    for key in ("ro.product.vendor.device","ro.vendor.build.fingerprint",
                "ro.product.vendor.model"):
        if key in report["properties"]:
            summary += [f"  - {key}={report['properties'][key]}"]
(output / "m55_vendor_audit.md").write_text("\n".join(summary)+"\n",encoding="utf-8")
print("M55_STOCK_VENDOR_ODM_AUDIT_OK",flush=True)
