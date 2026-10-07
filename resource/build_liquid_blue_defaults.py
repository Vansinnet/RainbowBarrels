"""Create a fixed-blue diagnostic from the five owned liquid material streams."""

import hashlib
import json
from pathlib import Path
import struct

from author_material import HASH32
from profile_exports import Cursor, pack_table, pack_words, template
from probe_defaults import defaults, encode


ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "analysis/liquid-bundle-v2-trial-24735202"
OUT = ROOT / "analysis/liquid-blue-defaults-24735202"
BLUE = struct.pack("<f", 240 / 360)
ZERO = struct.pack("<f", 0)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def color_template(data):
    c = Cursor(data)
    head = c.take(20)
    tables = [c.table(width) for width in (1, 3, 2, 5)]
    values = bytearray(c.take(c.words()[0]))
    count, = c.words()
    opaque = c.take(count * 5)
    last = c.table(2)
    if c.pos != len(data) or len([row for row in tables[3] if row[2] == HASH32]) != 1:
        raise ValueError("Unique authored material hue export")
    row = next(row for row in tables[3] if row[2] == HASH32)
    offset = row[3]
    if row[:2] != (0, 0) or row[4] != 4 or values[offset:offset + 4] != ZERO:
        raise ValueError("Expected zero hue material value")
    values[offset:offset + 4] = BLUE
    rebuilt = (head + b"".join(pack_table(rows) for rows in tables)
               + pack_words((len(values),)) + values + pack_words((count,)) + opaque
               + pack_table(last))
    if template(rebuilt)["reflection"] != template(data)["reflection"]:
        raise ValueError("Material reflection changed")
    return rebuilt


def color_material(source, is_parent):
    version, mo, ms, so, ss, tail, tail_size = struct.unpack_from("<7I", source)
    if version != 61 or mo != 28 or mo + ms > len(source):
        raise ValueError("Material envelope")
    material = color_template(source[mo:mo + ms])
    if len(material) != ms:
        raise ValueError("Unexpected template extent")
    edited = bytearray(source)
    edited[mo:mo + ms] = material
    if is_parent:
        if so != mo + ms or ss < 48 or so + ss > len(source):
            raise ValueError("Shader-bearing parent envelope")
        shader = source[so:so + ss]
        start, = struct.unpack_from("<I", shader, 20)
        rows = defaults(shader[start:])
        if rows[-1] != (HASH32, ZERO):
            raise ValueError("Expected zero hue GPU default")
        rows[-1] = (HASH32, BLUE)
        encoded = encode(rows)
        if len(encoded) > ss - start or shader[start:start + len(encoded) - 4] != encoded[:-4]:
            raise ValueError("GPU defaults layout drift")
        edited[so + start + len(encoded) - 4:so + start + len(encoded)] = BLUE
    elif so != 0xFFFFFFFF or ss != 0 or tail != 0xFFFFFFFF or tail_size != 0:
        raise ValueError("Unexpected child shader or tail")
    return bytes(edited)


def main():
    if OUT.exists():
        raise ValueError("Output already exists")
    base = json.loads((V2 / "report.json").read_text())
    changed = []
    payloads = {}
    for item in base["added_assets"]:
        if item["kind"] != "material":
            continue
        relative = item["stream"]
        original = (V2 / relative).read_bytes()
        name = item["identity"].rsplit("_", 1)[-1]
        if sha(original) != item["sha256"] or len(original) != item["bytes"]:
            raise ValueError("V2 material stream provenance: " + name)
        parent = name not in ("d11c8f091a39ef54", "62b838cfa247b2ca")
        candidate = color_material(original, parent)
        if len(candidate) != len(original) or candidate == original:
            raise ValueError("Fixed-blue material candidate: " + name)
        payloads[relative] = candidate
        changed.append({"identity": item["identity"], "stream": relative,
                        "v2_sha256": item["sha256"], "blue_sha256": sha(candidate),
                        "bytes": len(candidate), "shader_default_changed": parent})
    if len(changed) != 5 or sum(row["shader_default_changed"] for row in changed) != 3:
        raise ValueError("Exactly three parents and two children required")
    OUT.mkdir(parents=True)
    for relative, payload in payloads.items():
        dest = OUT / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
    (OUT / "report.json").write_text(json.dumps({
        "build": "24735202", "hue": 240, "bundle_sha256": base["candidate_bundle_sha256"],
        "status": "offline fixed-blue diagnostic; no installed game changes",
        "changed": changed,
    }, indent=2) + "\n")
    print(json.dumps(changed, indent=2))


if __name__ == "__main__":
    main()
