"""Read-only inventory of the three cloud-bound material texture/value slots."""

import hashlib
import json
from pathlib import Path
import struct

from profile_exports import Cursor


ROOT = Path(__file__).resolve().parents[1] / "analysis/liquid-stock-24735202"


def main():
    entries = json.loads((ROOT / "materials-provenance.json").read_text())["materials"]
    results = []
    for entry in entries:
        data = (ROOT / "materials" / entry["retained_file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["stream_sha256"]:
            raise ValueError("Retained pristine material hash changed")
        version, mo, ms, so, ss, _, _ = struct.unpack_from("<7I", data)
        if version != 61 or mo != 28 or mo + ms > len(data):
            raise ValueError("Material envelope")
        c = Cursor(data[mo:mo + ms])
        c.take(20)
        c.table(1)
        textures = c.table(3)
        c.table(2)
        reflection = c.table(5)
        length, = c.words()
        values = c.take(length)
        variables = []
        for kind, count, identity, offset, stride in reflection:
            if kind == 0 and count == 0 and offset + 4 <= len(values):
                variables.append({"hash": f"{identity:08x}", "value": struct.unpack_from("<f", values, offset)[0]})
        results.append({"material": entry["identity"], "parent": entry["parents"],
                        "shader_bytes": ss,
                        "textures": [{"channel": f"{channel:08x}", "resource": f"{resource:016x}"}
                                     for _, channel, resource in textures],
                        "scalar_values": variables})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
