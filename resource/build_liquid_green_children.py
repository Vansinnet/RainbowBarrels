"""Build a two-stream green child-only test from observed blue material children."""

import hashlib
import json
from pathlib import Path
import struct

from author_material import HASH32
from profile_exports import Cursor, template


ROOT = Path(__file__).resolve().parents[1]
BLUE = ROOT / "analysis/liquid-blue-defaults-24735202"
OUT = ROOT / "analysis/liquid-green-children-24735202"
CHILDREN = {"62b838cfa247b2ca", "d11c8f091a39ef54"}
BEFORE = struct.pack("<f", 2 / 3)
AFTER = struct.pack("<f", 1 / 3)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def edit_child(source):
    version, mo, ms, so, ss, tail, ts = struct.unpack_from("<7I", source)
    if (version != 61 or mo != 28 or mo + ms != len(source)
            or so != 0xFFFFFFFF or ss != 0 or tail != 0xFFFFFFFF or ts != 0):
        raise ValueError("Unexpected shaderless child envelope")
    c = Cursor(source[mo:])
    c.take(20)
    for width in (1, 3, 2):
        c.table(width)
    rows = c.table(5)
    value_size, = c.words()
    hue_rows = [row for row in rows if row[2] == HASH32]
    if len(hue_rows) != 1 or hue_rows[0][4] != 4 or hue_rows[0][3] + 4 > value_size:
        raise ValueError("Child hue export mismatch")
    offset = mo + c.pos + hue_rows[0][3]
    if source[offset:offset + 4] != BEFORE:
        raise ValueError("Child is not the pinned blue version")
    candidate = source[:offset] + AFTER + source[offset + 4:]
    if template(candidate[mo:])["reflection"] != template(source[mo:])["reflection"]:
        raise ValueError("Child material reflection changed")
    return candidate, offset


def main():
    if OUT.exists():
        raise ValueError("Output already exists")
    blue = json.loads((BLUE / "report.json").read_text())
    changes = []
    for row in blue["changed"]:
        name = row["identity"].rsplit("_", 1)[-1]
        if name not in CHILDREN:
            continue
        source = (BLUE / row["stream"]).read_bytes()
        if sha(source) != row["blue_sha256"]:
            raise ValueError("Blue child provenance: " + name)
        candidate, offset = edit_child(source)
        changes.append({"identity": row["identity"], "stream": row["stream"],
                        "blue_sha256": row["blue_sha256"], "green_sha256": sha(candidate),
                        "bytes": len(candidate), "hue_value_offset": offset})
        dest = OUT / row["stream"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(candidate)
    if len(changes) != 2:
        raise ValueError("Two shaderless child streams required")
    OUT.mkdir(exist_ok=True)
    (OUT / "report.json").write_text(json.dumps({
        "build": "24735202", "hue": 120,
        "status": "offline two-child green diagnostic; no installed game changes",
        "changes": changes,
    }, indent=2) + "\n")
    print(json.dumps(changes, indent=2))


if __name__ == "__main__":
    main()
