"""Pin material-export buffer sizes for the three persistent-fire shader families."""

import hashlib
import json
from pathlib import Path
import struct

from profile_exports import Cursor


ROOT = Path(__file__).resolve().parents[1] / "analysis/liquid-stock-24735202"
KNOWN = 0x2CC3DCEE


def main():
    rows = json.loads((ROOT / "materials-provenance.json").read_text())["materials"]
    result = []
    for item in rows:
        if not item["shader_bytes"]:
            continue
        data = (ROOT / "materials" / item["retained_file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["stream_sha256"]:
            raise ValueError("Stock material drift")
        _, _, _, so, ss, _, _ = struct.unpack_from("<7I", data)
        shader = data[so:so + ss]
        start, size = struct.unpack_from("<II", shader, 32)
        c = Cursor(shader[start:start + size])
        count, = c.words()
        groups = []
        for i in range(count):
            key, allocation = c.words(2)
            c.table(4)
            n, = c.words()
            buffers, material = [], None
            for j in range(n):
                descriptors = c.table(5)
                length, offset = c.words(2)
                buffers.append({"index": j, "size": length, "offset": offset,
                                "fields": len(descriptors)})
                if any(entry[2] == KNOWN for entry in descriptors):
                    material = {"buffer": j, "size": length, "offset": offset,
                                "used": max(entry[3] + max(1, entry[1]) * entry[4]
                                            for entry in descriptors)}
            c.table(7)
            techniques, = c.words()
            c.take(17 * techniques + 8)
            if material:
                groups.append({"group": i, "key": f"{key:08x}", "allocation": allocation,
                               "material": material, "buffers": buffers if i in (0, 1, count - 1) else None})
        if c.pos != len(c.data):
            raise ValueError("Registration table exhaustion")
        result.append({"material": item["identity"], "groups": count,
                       "material_group_count": len(groups), "registered": groups})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
