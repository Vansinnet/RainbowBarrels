"""Independent full readback of the expanded 360-degree ground-fire wheel."""

import hashlib
import json
from pathlib import Path
import struct

from analyze_effects import decode_bundle_parts
from author_material import HASH32
from inspect_stock import murmur64
from profile_exports import Cursor
from probe_defaults import defaults, encode
from profile_particles import profile


ROOT = Path(__file__).resolve().parents[1] / "analysis"
BASE = ROOT / "liquid-bundle-v2-trial-24735202"
WHEEL = ROOT / "liquid-hue-wheel-24735202"
PACKAGE = "b224998193576995"
CHILDREN = {"62b838cfa247b2ca", "d11c8f091a39ef54"}
RIM = "4cd51280796476b3"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def float_locations(data, child):
    version, mo, ms, so, ss, _, _ = struct.unpack_from("<7I", data)
    if version != 61 or mo != 28 or mo + ms > len(data):
        raise ValueError("Material envelope")
    c = Cursor(data[mo:mo + ms])
    c.take(20)
    for width in (1, 3, 2):
        c.table(width)
    rows = c.table(5)
    length, = c.words()
    matches = [row for row in rows if row[2] == HASH32]
    if len(matches) != 1 or matches[0][4] != 4 or matches[0][3] + 4 > length:
        raise ValueError("Template hue export")
    offsets = [mo + c.pos + matches[0][3]]
    if child:
        if so != 0xFFFFFFFF or ss != 0:
            raise ValueError("Shaderless child expected")
    else:
        if so != mo + ms or ss <= 48:
            raise ValueError("Direct shader material expected")
        shader = data[so:so + ss]
        start, = struct.unpack_from("<I", shader, 20)
        rows = defaults(shader[start:])
        if rows[-1] != (HASH32, bytes(4)):
            raise ValueError("Original rim shader default")
        offsets.append(so + start + len(encode(rows)) - 4)
    if any(data[offset:offset + 4] != bytes(4) for offset in offsets):
        raise ValueError("Pinned zero-default material source")
    return offsets


def main():
    report = json.loads((WHEEL / "report.json").read_text())
    baseline = json.loads((BASE / "report.json").read_text())
    source = (BASE / "bundle" / PACKAGE).read_bytes()
    candidate = (WHEEL / "bundle" / PACKAGE).read_bytes()
    if (sha(source) != report["base_bundle_sha256"] == baseline["candidate_bundle_sha256"]
            or sha(candidate) != report["candidate_bundle_sha256"]):
        raise ValueError("Liquid bundle identity")
    original, _ = decode_bundle_parts(source, lambda block: block)
    records, padding = decode_bundle_parts(candidate, lambda block: block)
    if (len(original) != 110 or len(records) != 1910 or original != records[:110]
            or len(report["added_material_streams"]) != 1080
            or len(report["generated_particles"]) != 720 or any(padding)):
        raise ValueError("Existing stock and custom resources unchanged")
    existing_materials = {item["identity"].rsplit("_", 1)[-1]: item for item in baseline["added_assets"]
                          if item["kind"] == "material"}
    base_bytes = {name: (BASE / item["stream"]).read_bytes() for name, item in existing_materials.items()
                  if name in CHILDREN | {RIM}}
    base_offsets = {name: float_locations(data, name in CHILDREN) for name, data in base_bytes.items()}
    streams = {item["name"]: item for item in report["added_material_streams"]}
    particles = {item["name"]: item for item in report["generated_particles"]}
    for hue in range(360):
        material_ids = {}
        for name in CHILDREN | {RIM}:
            path = f"content/fx/materials/rainbow_barrels/liquid_{name}_hue_{hue:03d}"
            row = streams[path]
            data = (WHEEL / row["stream"]).read_bytes()
            source_data = base_bytes[name]
            if row["hue"] != hue or sha(data) != row["sha256"] or row["bytes"] != len(data):
                raise ValueError("Variant material provenance")
            expected = bytearray(source_data)
            for offset in base_offsets[name]:
                expected[offset:offset + 4] = struct.pack("<f", hue / 360)
            if data != expected:
                raise ValueError("Unrelated variant material byte changed")
            material_ids[name] = murmur64(path)
        for stem, kind in (("fire_lingering_filled", "filled"), ("fire_lingering_rim", "rim")):
            path = f"content/fx/particles/rainbow_barrels/{stem}_hue_{hue:03d}"
            row = particles[path]
            raw = next((record for identity, record, _ in records[110:]
                        if identity[:2] == (murmur64("particles"), murmur64(path))), None)
            if not raw or row["hue"] != hue or row["kind"] != kind or sha(raw) != row["sha256"]:
                raise ValueError("Variant particle identity")
            billboards = [cloud for cloud in profile(raw)["clouds"] if cloud["visualizer_type"] == 0]
            if len(billboards) != (2 if kind == "filled" else 1):
                raise ValueError("Unexpected billboard count")
            expected_materials = ({material_ids[name] for name in CHILDREN} if kind == "filled"
                                  else {material_ids[RIM]})
            if {int(cloud["material_candidate"], 16) for cloud in billboards} != expected_materials:
                raise ValueError("Variant billboard material binding")
    material_index = {(identity[0], identity[1]): raw for identity, raw, _ in records[110:]
                      if identity[0] == murmur64("material")}
    for path, row in streams.items():
        key = murmur64(path)
        pointer = material_index.get((murmur64("material"), key))
        if pointer is None or pointer[38:] != f"data/rb/{key:016x}".encode() + bytes(4):
            raise ValueError("Variant material index pointer")
    if len(material_index) != 1080 or len(streams) != 1080 or len(particles) != 720:
        raise ValueError("Unexpected variant identity count")
    print(json.dumps({"bundle_sha256": sha(candidate), "original_resources_preserved": 110,
                      "hue_values": 360, "material_variants": len(streams),
                      "particle_variants": len(particles),
                      "status": "offline structural readback; engine color selection untested"}, indent=2))


if __name__ == "__main__":
    main()
