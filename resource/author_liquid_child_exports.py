"""Expose the persistent-fire hue scalar through two shaderless child materials."""

import hashlib
import json
from pathlib import Path
import struct

from author_material import HASH32
from author_material_families import material_template
from inspect_stock import murmur64
from profile_exports import template


ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "analysis/liquid-stock-24735202"
BASE = ROOT / "analysis/liquid-hue-materials-24735202"
OUT = ROOT / "analysis/liquid-hue-materials-v2-24735202"
CHILDREN = {"d11c8f091a39ef54": "1cc58f33452ca960",
            "62b838cfa247b2ca": "62c7bb3aa1cac9c2"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def author_child(source, name, parent):
    version, material_offset, material_size, shader_offset, shader_size, tail_offset, tail_size = struct.unpack_from(
        "<7I", source)
    if (version != 61 or material_offset != 28 or material_offset + material_size != len(source)
            or shader_offset != 0xFFFFFFFF or shader_size != 0
            or tail_offset != 0xFFFFFFFF or tail_size != 0):
        raise ValueError("Unexpected shaderless child envelope: " + name)
    original = source[material_offset:]
    before = template(original)
    if any(row[2] == HASH32 for row in before["reflection"]):
        raise ValueError("Child already exposes the hue scalar: " + name)
    if struct.unpack_from("<Q", original, 4)[0] != int(parent, 16):
        raise ValueError("Stock child parent changed: " + name)
    rewritten = bytearray(original)
    custom_parent = murmur64("content/fx/materials/rainbow_barrels/liquid_" + parent)
    struct.pack_into("<Q", rewritten, 4, custom_parent)
    material = material_template(bytes(rewritten), True)
    after = template(material)
    if (after["reflection"][:-1] != before["reflection"]
            or after["reflection"][-1] != (0, 0, HASH32, before["values_size"], 4)
            or after["values_size"] != before["values_size"] + 4):
        raise ValueError("Child scalar export delta: " + name)
    outer = bytearray(source[:material_offset])
    struct.pack_into("<I", outer, 8, len(material))
    candidate = bytes(outer) + material
    return candidate, {"material": name, "kind": "shaderless_child",
                       "parent": parent, "custom_parent": f"{custom_parent:016x}",
                       "export_offset": before["values_size"],
                       "source_sha256": sha(source), "candidate_sha256": sha(candidate),
                       "source_bytes": len(source), "candidate_bytes": len(candidate)}


def main():
    if OUT.exists():
        raise ValueError("Output already exists")
    stocks = {item["identity"]: item for item in json.loads(
        (STOCK / "materials-provenance.json").read_text())["materials"]}
    base_reports = json.loads((BASE / "provenance.json").read_text())["materials"]
    payloads = {}
    reports = []
    for report in base_reports:
        name = report["material"]
        payload = (BASE / (name + ".material")).read_bytes()
        if sha(payload) != report["candidate_sha256"]:
            raise ValueError("Parent candidate changed: " + name)
        payloads[name + ".material"] = payload
        reports.append(dict(report, kind="shader_parent"))
    for name, parent in CHILDREN.items():
        stock = stocks[name]
        source = (STOCK / "materials" / stock["retained_file"]).read_bytes()
        if sha(source) != stock["stream_sha256"]:
            raise ValueError("Stock child changed: " + name)
        candidate, report = author_child(source, name, parent)
        payloads[name + ".material"] = candidate
        reports.append(report)
    if len(payloads) != 5 or len(reports) != 5:
        raise ValueError("Three shader parents and two child exports required")
    OUT.mkdir(parents=True)
    for filename, payload in payloads.items():
        (OUT / filename).write_bytes(payload)
    (OUT / "provenance.json").write_text(json.dumps({
        "build": "24735202",
        "status": "offline child-export candidates; unregistered and untested in game",
        "materials": reports,
    }, indent=2) + "\n")
    print(json.dumps([{"material": row["material"], "kind": row["kind"],
                       "candidate_sha256": row["candidate_sha256"]} for row in reports], indent=2))


if __name__ == "__main__":
    main()
