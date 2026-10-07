"""Independent exact-byte verification of the two green child material streams."""

import hashlib
import json
from pathlib import Path
import struct

from author_material import HASH32
from profile_exports import Cursor, template


ROOT = Path(__file__).resolve().parents[1] / "analysis"
BLUE = ROOT / "liquid-blue-defaults-24735202"
GREEN = ROOT / "liquid-green-children-24735202"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    report = json.loads((GREEN / "report.json").read_text())
    if report["hue"] != 120 or len(report["changes"]) != 2:
        raise ValueError("Green child test profile")
    for row in report["changes"]:
        before = (BLUE / row["stream"]).read_bytes()
        after = (GREEN / row["stream"]).read_bytes()
        version, mo, ms, so, ss, tail, tail_size = struct.unpack_from("<7I", before)
        if (version != 61 or mo != 28 or mo + ms != len(before) or so != 0xFFFFFFFF
                or ss != 0 or tail != 0xFFFFFFFF or tail_size != 0
                or sha(before) != row["blue_sha256"] or sha(after) != row["green_sha256"]
                or len(after) != len(before) == row["bytes"]):
            raise ValueError("Pinned child identity or envelope")
        c = Cursor(before[mo:])
        c.take(20)
        for width in (1, 3, 2):
            c.table(width)
        reflection = c.table(5)
        size, = c.words()
        matching = [entry for entry in reflection if entry[2] == HASH32]
        if len(matching) != 1 or matching[0][4] != 4 or matching[0][3] + 4 > size:
            raise ValueError("Exact child hue field")
        offset = mo + c.pos + matching[0][3]
        expected = (before[:offset] + struct.pack("<f", 1 / 3) + before[offset + 4:])
        if (row["hue_value_offset"] != offset or before[offset:offset + 4] != struct.pack("<f", 2 / 3)
                or after != expected or template(after[mo:])["reflection"] != reflection):
            raise ValueError("Unrelated byte changed in green child")
    print(json.dumps({"verified_children": 2, "hue": 120,
                      "status": "exact child-value-only delta; runtime color untested"}, indent=2))


if __name__ == "__main__":
    main()
