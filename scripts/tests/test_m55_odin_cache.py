#!/usr/bin/env python3
"""Fast synthetic regression for original UN1CA pinned Odin-cache bridge."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "m55_prepare_odin_cache.py"
SAMPLES = [
    ("stock","SM-M556B","INS","M556BXXS4BYH2"),
    ("donor","SM-S901E","TUR","S901EXXSEGZH4"),
]

with tempfile.TemporaryDirectory(prefix="m55-odin-cache-") as temp:
    root = Path(temp)
    for mode, model, region, pda in SAMPLES:
        archived = root / (mode + ".zip")
        with zipfile.ZipFile(archived,"w") as z:
            for part in ("BL","AP"):
                z.writestr(f"{part}_{pda}_TEST.tar.md5", b"test_" + part.encode())
        dest = root / ("odin-" + mode)
        subprocess.run(
            [sys.executable, str(SCRIPT), mode, str(archived), str(dest)],
            check=True, capture_output=True, text=True
        )
        folder = dest / (model + "_" + region)
        assert (folder / ".downloaded").is_file(), mode
        assert (folder / ("AP_" + pda + "_TEST.tar.md5")).read_bytes() == b"test_AP", mode
        assert (folder / ("BL_" + pda + "_TEST.tar.md5")).read_bytes() == b"test_BL", mode
        assert (folder / ".downloaded").read_text().startswith(pda + "/"), mode

    # Rejected wrong-PDA input must never be accepted as the target's
    # pinned firmware cache.
    bad = root / "wrong.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("AP_WRONG_TEST.tar.md5", b"bad")
        z.writestr("BL_WRONG_TEST.tar.md5", b"bad")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "stock", str(bad), str(root / "wrong-odin")],
        capture_output=True, text=True
    )
    assert result.returncode != 0

print("PASS: original UN1CA M55/S22 pinned FUS Odin cache regression")
