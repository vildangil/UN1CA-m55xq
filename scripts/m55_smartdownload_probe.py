#!/usr/bin/env python3
"""Read-only Samsung SmartDownload metadata probe, adapted from Bifrost 2.x.

Queries exact M55 builds; never downloads firmware payloads or logs credentials.
Bifrost source: https://github.com/zacharee/Bifrost (MIT-licensed).
"""
from __future__ import annotations
import hashlib
import json
import os
import struct
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HOST = "https://neofussvr.sslcs.cdngc.net/"
MODEL = "SM-M556B"
REGION = "INS"
PDAS = ("M556BXXS4BYH2", "M556BXXS4CYL1")
AUTH_DATA_URL = ("https://raw.githubusercontent.com/zacharee/Bifrost/"
                 "ed73a034d3b27d84c68b2c21622a9de6618455de/"
                 "common/src/commonMain/composeResources/files/auth_param.dat")
SHIFT = (0, 5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12, 1, 6, 11)


def http(method, url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as rsp:
            return rsp.read(3_000_000), rsp.headers, rsp.status
    except urllib.error.HTTPError as error:
        return error.read(3_000_000), error.headers, error.code


def xml_data(node, name, value):
    ET.SubElement(ET.SubElement(node, name), "Data").text = str(value)


def xml_text(node, name, value):
    ET.SubElement(node, name).text = str(value)


def payload(kind, firmware="", nonce=""):
    root = ET.Element("FUSMsg")
    hdr = ET.SubElement(root, "FUSHdr")
    for key, val in (("ProtoVer", "1"), ("SessionID", "0"), ("MsgID", "1")):
        xml_text(hdr, key, val)
    body = ET.SubElement(root, "FUSBody")
    put = ET.SubElement(body, "Put")
    if kind == "history":
        for key, val in (("ACCESS_MODE", "1"), ("BINARY_MODEL_NAME", MODEL),
                         ("BINARY_LOCAL_CODE", REGION)):
            xml_data(put, key, val)
    else:
        xml_text(put, "CmdID", "1")
        for key, val in (("REQUEST_TYPE", "2"),
                         ("BINARY_SW_VERSION", firmware),
                         ("DEVICE_SN_NUMBER", ""),
                         ("BINARY_LOCAL_CODE", REGION),
                         ("BINARY_MODEL_NAME", MODEL),
                         ("ACCESS_MODE", "1"), ("BINARY_NATURE", "1"),
                         ("LOGIC_CHECK",
                          "".join(firmware[ord(n) & 15] for n in nonce)
                          if len(firmware) >= 16 else "")):
            xml_data(put, key, val)
        language = ET.SubElement(put, "CLIENT_LANGUAGE")
        xml_text(language, "Type", "String")
        xml_text(language, "Type", "ISO 3166-1-alpha-3")
        xml_text(language, "Data", "1033")
        get = ET.SubElement(body, "Get")
        xml_text(get, "CmdID", "2")
        ET.SubElement(get, "BINARY_SW_VERSION")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def get_value(root, name):
    el = root.find(".//FUSBody/Put/" + name + "/Data")
    return el.text if el is not None and el.text is not None else ""


def parse_xml(raw):
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return None


def status(root):
    if root is None:
        return "invalid_xml"
    return root.findtext(".//FUSBody/Results/Status", default="unknown")


def transform_auth(data, nonce):
    """Python translation of CryptUtils.authenticateBlock in Bifrost 2.x."""
    if len(nonce) < 16 or len(data) < 56:
        raise ValueError("Bifrost auth data or Samsung nonce too short")
    h = struct.unpack_from("<14I", data)
    size1, size2, size3 = h[3], h[5], h[11]
    base = 56
    temp = [0] * 320
    for i, ch in enumerate(nonce[:16].encode("ascii")):
        temp[i] = ch
    v15 = [0] * 64

    def read(offset, length):
        if offset < 0 or base + offset + length > len(data):
            raise ValueError("Bifrost auth table index out of bounds")
        return data[base + offset : base + offset + length]

    for j in range(9):
        src = j * 32
        nxt = (j + 1) * 32
        mid = src + 16
        for idx in range(16):
            temp[src + 16 + idx] = temp[src + SHIFT[idx]]
        for i in range(4):
            i4, i16 = 4 * i, 16 * i
            block_base = j * 16 + i4
            table_offset = size1 + size2 + size3 + 6144 * (i + j * 4)
            for k in range(4):
                val = temp[mid + i4 + k]
                block_id = block_base + k
                src_ptr = read((block_id << 12) + (val << 4), 16)
                sel = read(size1 + size2 + (block_id << 5), 32)
                out_idx = i16 + (k << 2)
                for o in range(4):
                    acc = 0
                    for bit in range(8):
                        p = sel[o * 8 + bit]
                        idx = (p >> 3) & 31
                        byte = src_ptr[idx] if idx < 16 else 0
                        acc |= ((byte >> (7 - (p & 7))) & 1) << (7 - bit)
                    v15[out_idx + o] = acc & 255
            for k in range(4):
                a, b, c, d = (v15[i16 + k + p] for p in (0, 4, 8, 12))
                table = read(table_offset + 1536 * k, 1536)
                hi1 = ((a & 240) | (b >> 4)) & 255
                lo1 = (((a & 15) << 4) | (b & 15)) & 255
                v6 = (16 * table[hi1] ^ table[256 + lo1]) & 255
                hi2 = ((c & 240) | (d >> 4)) & 255
                lo2 = (((c & 15) << 4) | (d & 15)) & 255
                v7 = (16 * table[512 + hi2] ^ table[768 + lo2]) & 255
                hi3 = ((v6 & 240) | (v7 >> 4)) & 255
                lo3 = (((v6 & 15) << 4) | (v7 & 15)) & 255
                temp[nxt + i4 + k] = (16 * table[1024 + hi3] ^ table[1280 + lo3]) & 255
    result = bytes(read(size1 + (idx << 8) + temp[SHIFT[idx] + 288], 1)[0]
                   for idx in range(16))
    return result.hex()


class SmartClient:
    def __init__(self):
        self.session_id = ""
        self.nonce = ""
        self.auth = ""
        self.auth_data = None

    def new_nonce(self):
        raw, headers, http_status = http("POST", HOST + "NF_SmartDownloadGenerateNonce.do",
                                         b"", self.headers())
        if http_status != 200:
            raise RuntimeError("SmartDownload nonce HTTP " + str(http_status))
        self.update(headers)
        if not self.nonce:
            raise RuntimeError("SmartDownload did not provide NONCE header")
        self.auth_data = urllib.request.urlopen(AUTH_DATA_URL, timeout=35).read(1_000_000)
        self.auth = transform_auth(self.auth_data, self.nonce[:16])

    def update(self, headers):
        nonce = headers.get("NONCE", "")
        if nonce:
            self.nonce = nonce[:16]
            if self.auth_data is not None:
                # Samsung rotates NONCE after each response; the signature
                # must be recomputed before the following BinaryInform.
                self.auth = transform_auth(self.auth_data, self.nonce[:16])
        cookie = headers.get("Set-Cookie", "")
        for item in cookie.split(";"):
            if item.strip().startswith("JSESSIONID="):
                self.session_id = item.strip().split("=", 1)[1]
                break

    def headers(self, history=False):
        nonce = self.nonce
        signature = self.auth
        if history and nonce:
            ha = hashlib.md5(("auth:" + nonce + ":00000001").encode()).hexdigest()
            hb = hashlib.md5(("interface:" + MODEL).encode()).hexdigest()
            signature = hashlib.md5((ha + ":FUS:" + hb).encode()).hexdigest()
        auth_hdr = ('FUS nonce="' + nonce + '", signature="' + signature + '", '
                    'nc="' + ("00000001" if history else "") + '", '
                    'type="' + ("auth" if history else "") + '", '
                    'realm="' + ("interface" if history else "") + '"')
        cookies = "JSESSIONID=" + self.session_id + ";SESSION=" + self.session_id
        return {"Authorization": auth_hdr, "User-Agent": "SMART 2.0",
                "Cookie": cookies, "Set-Cookie": cookies,
                "Content-Type": "application/xml"}

    def post(self, endpoint, body, history=False):
        raw, headers, code = http("POST", HOST + endpoint, body, self.headers(history))
        self.update(headers)
        return parse_xml(raw), code


def history_from_fota():
    url = "https://fota-cloud-dn.ospserver.net/firmware/INS/SM-M556B/version.xml"
    raw, _, code = http("GET", url, headers={"User-Agent": "Kiss2.0_FUS"})
    root = parse_xml(raw)
    if code != 200 or root is None:
        return []
    matches = [e.text.strip() for e in root.findall(".//version/upgrade/value")
               if e.text and e.text.strip()]
    latest = root.findtext(".//version/latest", default="")
    return ([latest] if latest else []) + matches


def main():
    report = {"model": MODEL, "region": REGION, "requests": []}
    try:
        historical = history_from_fota()
        report["fota_history_matches"] = [v for v in historical
                                          if any(pda in v for pda in PDAS)]
        print("FOTA historical entries matching target builds:",
              len(report["fota_history_matches"]), flush=True)
        client = SmartClient()
        client.new_nonce()
        h, code = client.post("SmartHistory.do", payload("history"), history=True)
        items = []
        if h is not None:
            for entry in h.findall(".//BINARY_INFO"):
                d = entry.findtext("BINARY_SW_VERSION/Data", default="")
                if d:
                    items.append(d)
        report["smart_history_http"] = code
        report["smart_history_status"] = status(h)
        report["smart_history_matches"] = [v for v in items
                                           if any(p in v for p in PDAS)]
        print("SmartHistory: HTTP", code, "entries", len(items),
              "matching", len(report["smart_history_matches"]), flush=True)
        latest_version = next((v for v in historical if v.startswith("M556B")),
                              items[-1] if items else "")
        latest_pda = latest_version.split("/")[0] if latest_version else ""
        testing = list(PDAS)
        if latest_pda and latest_pda not in testing:
            testing.append(latest_pda)
        report["fota_exact_versions"] = [v for v in historical
                                         if any(pda in v for pda in PDAS)]
        report["smart_history_exact_versions"] = [v for v in items
                                                  if any(pda in v for pda in PDAS)]
        for pda in testing:
            from_history = next((v for v in items + historical if pda in v), None)
            if from_history:
                parts = from_history.split("/")
                if len(parts) == 3:
                    parts.append(parts[0])
                version = "/".join(parts)
            else:
                version = pda + "/" + pda + "/" + pda + "/" + pda
            res, status_code = client.post(
                "NF_SmartDownloadBinaryInform.do", payload("binary", version, client.nonce))
            served_file = get_value(res, "BINARY_NAME") if res is not None else ""
            reported_version = get_value(res, "BINARY_SW_VERSION") if res is not None else ""
            exact = status(res) in ("200", "S00") and pda in served_file
            report["requests"].append({
                "requested_pda": pda, "requested_version": version,
                "response_http": status_code, "response_status": status(res),
                "exact_match": exact, "served_build": pda if exact else
                (next((v for v in PDAS if v in served_file), None)),
                "served_version_matches_request": pda in reported_version,
            })
            print(pda, "HTTP", status_code, "FUS status", status(res),
                  "EXACT MATCH" if exact else "not confirmed", flush=True)
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
        print("SmartDownload probe error:", report["error"], flush=True)
    Path("m55-smartdownload-probe.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("### Bifrost 2.x SmartDownload probe: M55 old builds\n")
            for item in report["requests"]:
                out.write("- " + item["requested_pda"] + ": " +
                          ("exact-match available" if item["exact_match"]
                           else "not available / not confirmed") +
                          " (HTTP " + str(item["response_http"]) +
                          ", status " + item["response_status"] + ")\n")
            if "error" in report:
                out.write("- Probe error: " + report["error"] + "\n")
    if "error" in report:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
