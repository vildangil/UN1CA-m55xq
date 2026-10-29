#!/usr/bin/env python3
"""Read-only Samsung FOTA latest-version probe for the M55 port."""
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

csc = os.environ.get("M55_CSC", "INS").strip().upper()
if not re.fullmatch(r"[A-Z0-9]{3}", csc):
    raise SystemExit("M55_CSC must be a three-character Samsung CSC")

results = []
for model, region in (("SM-M556B", csc), ("SM-S901E", "TUR")):
    url = f"https://fota-cloud-dn.ospserver.net/firmware/{region}/{model}/version.xml"
    request = urllib.request.Request(url, headers={
        "User-Agent": f"samsung {model} SyncML DM Client"
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read(512 * 1024))
    latest = next((el.text for el in root.iter()
                   if el.tag.rsplit("}", 1)[-1] == "latest" and el.text), None)
    if not latest:
        raise SystemExit(f"No latest firmware entry for {model} ({region})")
    msg = f"{model} / {region}: latest FOTA = {latest}"
    print(msg, flush=True)
    results.append(msg)

print("FOTA latest is diagnostic only; it does NOT pin M55 One UI 7.", flush=True)
summary = os.getenv("GITHUB_STEP_SUMMARY")
if summary:
    with open(summary, "a", encoding="utf-8") as out:
        out.write("### Firmware metadata check\n")
        for item in results:
            out.write(f"- {item}\n")
        out.write("\nFOTA reports latest releases; it does not select an older One UI 7 image.\n")
