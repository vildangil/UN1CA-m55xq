#!/usr/bin/env python3
"""Check exact older M55 builds on Samsung FUS without downloading gigabytes."""
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

from samloader import fusclient, imei, request

MODEL = "SM-M556B"
CSC = "INS"
# Publicly documented type-allocation code for SM-M556B, not a user's IMEI.
PUBLIC_TAC = "35280753"
VERSIONS = {
    "oneui7": "M556BXXS4BYH2/M556BODM4BYH2/M556BXXS4BYH2/M556BXXS4BYH2",
    "oneui8": "M556BXXS4CYL1/M556BODM4CYL1/M556BXXS4CYL1/M556BXXS4CYL1",
}
results = {}

for label, version in VERSIONS.items():
    requested_pda = version.split("/")[0]
    attempts = []
    for n in range(2):
        try:
            # Never print or persist the synthesized request identifier.
            synthetic_imei = imei.generate_random_imei(PUBLIC_TAC)
            client = fusclient.FUSClient()
            payload = request.binaryinform(version, MODEL, CSC, synthetic_imei, client.nonce)
            response = client.makereq("NF_DownloadBinaryInform.do", payload)
            root = ET.fromstring(response)
            code = root.findtext("./FUSBody/Results/Status", default="unknown")
            filename = root.findtext("./FUSBody/Put/BINARY_NAME/Data", default="")
            size_raw = root.findtext("./FUSBody/Put/BINARY_BYTE_SIZE/Data", default="0")
            exact = code == "200" and requested_pda in filename
            attempts.append({"status": code, "exact_match": exact,
                             "name": filename if exact else None,
                             "size_bytes": int(size_raw) if exact else None})
            if exact:
                break
        except Exception as error:
            # Avoid printing request payloads / private session headers.
            attempts.append({"status": type(error).__name__, "exact_match": False})
    ok = any(a["exact_match"] for a in attempts)
    result = next((a for a in attempts if a["exact_match"]), attempts[-1])
    results[label] = {"requested": requested_pda,
                      "available": ok,
                      "server_status": result["status"],
                      "filename": result.get("name"),
                      "size_bytes": result.get("size_bytes")}
    print(f"{label}: {requested_pda} -> " +
          ("EXACT MATCH AVAILABLE" if ok else "unavailable / not confirmed") +
          f" (status={result['status']})", flush=True)

Path("m55-fus-probe.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
if os.getenv("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"oneui7_available={str(results['oneui7']['available']).lower()}\n")
if os.getenv("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
        out.write("### Samsung FUS exact-build probe (no download)\n\n")
        for item in results.values():
            out.write(f"- {item['requested']}: " +
                      ("Available (exact match)" if item["available"] else
                       "Not confirmed; **do not download latest as substitute**") + "\n")
        out.write("\nA FUS failure does not rule out an external archived source.\n")
