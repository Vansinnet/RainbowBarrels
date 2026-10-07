"""Independently verify exact float-only deltas in fixed-blue material streams."""

import hashlib
import json
from pathlib import Path
import struct

from author_material import HASH32
from profile_exports import Cursor
from probe_defaults import defaults, encode


ROOT = Path(__file__).resolve().parents[1] / "analysis"
V2 = ROOT / "liquid-bundle-v2-trial-24735202"
OUT = ROOT / "liquid-blue-defaults-24735202"
BLUE = struct.pack("<f", 2 / 3)
ZERO = bytes(4)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def main():
    report = json.loads((OUT / "report.json").read_text())
    base = json.loads((V2 / "report.json").read_text())
    assets = {item["stream"]: item for item in base["added_assets"] if item["kind"] == "material"}
    if report["bundle_sha256"] != base["candidate_bundle_sha256"] or report["hue"] != 240:
        raise ValueError("Bundle or test hue changed")
    checked = []
    for row in report["changed"]:
        item = assets[row["stream"]]
        original = (V2 / row["stream"]).read_bytes()
        candidate = (OUT / row["stream"]).read_bytes()
        if (sha(original) != row["v2_sha256"] or sha(candidate) != row["blue_sha256"]
                or len(original) != len(candidate) or item["sha256"] != row["v2_sha256"]):
            raise ValueError("Pinned stream identity: " + row["stream"])
        version, mo, ms, so, ss, tail, tail_size = struct.unpack_from("<7I", original)
        if version != 61 or mo != 28 or mo + ms > len(original):
            raise ValueError("Material61 envelope")
        c = Cursor(original[mo:mo + ms])
        c.take(20)
        c.table(1)
        c.table(3)
        c.table(2)
        rows = c.table(5)
        size, = c.words()
        base_offset = mo + c.pos
        matches = [entry for entry in rows if entry[2] == HASH32]
        if len(matches) != 1 or matches[0][4] != 4 or matches[0][3] + 4 > size:
            raise ValueError("Scalar export identity or size")
        offsets = [base_offset + matches[0][3]]
        if row["shader_default_changed"]:
            if so != mo + ms or ss <= 48:
                raise ValueError("Expected parent shader")
            shader = original[so:so + ss]
            start, = struct.unpack_from("<I", shader, 20)
            values = defaults(shader[start:])
            if values[-1] != (HASH32, ZERO):
                raise ValueError("Expected original parent GPU default")
            offsets.append(so + start + len(encode(values)) - 4)
        elif so != 0xFFFFFFFF or ss != 0 or tail != 0xFFFFFFFF or tail_size != 0:
            raise ValueError("Expected shaderless child")
        expected = bytearray(original)
        for offset in offsets:
            if expected[offset:offset + 4] != ZERO:
                raise ValueError("Default already nonzero")
            expected[offset:offset + 4] = BLUE
        if candidate != expected or row["bytes"] != len(candidate):
            raise ValueError("Unrelated material byte changed: " + row["stream"])
        checked.append({"stream": row["stream"], "blue_float_offsets": offsets,
                        "sha256": sha(candidate)})
    if len(checked) != 5 or len([row for row in checked if len(row["blue_float_offsets"]) == 2]) != 3:
        raise ValueError("Three parents and two children required")
    print(json.dumps({"status": "exact float-only readback; visual outcome pending",
                      "materials": checked}, indent=2))


if __name__ == "__main__":
    main()
