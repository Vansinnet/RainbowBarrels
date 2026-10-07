"""Inspect one target material's shader-group and export layout without edits."""

import hashlib
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "analysis/stock-materials-24735202/9cda55b98bbfc8ff.material"
PROVENANCE = ROOT / "analysis/stock-materials-24735202/provenance.json"


def inspect():
    source = PATH.read_bytes()
    entry = next(r for r in json.loads(PROVENANCE.read_text())["materials"]
                 if r["identity"] == PATH.stem)
    if hashlib.sha256(source).hexdigest() != entry["source_sha256"]:
        raise ValueError("Stock material drift")
    header = struct.unpack_from("<7I", source)
    shader = source[header[3]:header[3] + header[4]]
    fields = struct.unpack_from("<12I", shader)
    group_start, group_size = fields[8:10]
    if header[0] != 61 or fields[0] != 43 or group_start + group_size > len(shader):
        raise ValueError("Material/shader framing")
    group = shader[group_start:group_start + group_size]
    return {"material_header": header, "shader_header": fields,
            "group_prefix": struct.unpack_from("<6I", group),
            "group_size": group_size, "group_hex_head": group[:128].hex(),
            "material_exports": entry["variables"]}


if __name__ == "__main__":
    print(json.dumps(inspect(), indent=2))
