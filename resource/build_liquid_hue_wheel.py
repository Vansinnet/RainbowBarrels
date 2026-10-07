"""Author 360 isolated filled-fire and rim variants from pinned liquid candidates."""

import json
from pathlib import Path
import struct

from analyze_effects import decode_bundle_parts
from author_material import HASH32
from build_green_bundle import bundle, resource_record, sha
from inspect_stock import murmur64
from profile_exports import Cursor, template
from probe_defaults import defaults, encode


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "analysis/liquid-bundle-v2-trial-24735202"
BLUE = ROOT / "analysis/liquid-blue-defaults-24735202"
GREEN = ROOT / "analysis/liquid-green-children-24735202"
OUT = ROOT / "analysis/liquid-hue-wheel-24735202"
PACKAGE = "b224998193576995"
BASE_SHA = "6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d"
CHILDREN = {"62b838cfa247b2ca", "d11c8f091a39ef54"}
RIM = "4cd51280796476b3"
STEMS = {"filled": "fire_lingering_filled", "rim": "fire_lingering_rim"}


def material_variant(source, hue, shader_default):
    version, mo, ms, so, ss, _, _ = struct.unpack_from("<7I", source)
    if version != 61 or mo != 28 or mo + ms > len(source):
        raise ValueError("Liquid material envelope")
    c = Cursor(source[mo:mo + ms])
    c.take(20)
    for width in (1, 3, 2):
        c.table(width)
    rows = c.table(5)
    size, = c.words()
    match = [row for row in rows if row[2] == HASH32]
    if len(match) != 1 or match[0][:2] != (0, 0) or match[0][4] != 4 or match[0][3] + 4 > size:
        raise ValueError("Authored liquid hue reflection")
    offset = mo + c.pos + match[0][3]
    if source[offset:offset + 4] != bytes(4):
        raise ValueError("Expected zero material default")
    value = struct.pack("<f", hue / 360)
    result = bytearray(source)
    result[offset:offset + 4] = value
    if shader_default:
        if so != mo + ms or ss < 48:
            raise ValueError("Expected direct rim shader")
        shader = source[so:so + ss]
        start, = struct.unpack_from("<I", shader, 20)
        values = defaults(shader[start:])
        if values[-1] != (HASH32, bytes(4)):
            raise ValueError("Expected zero rim GPU default")
        gpu_offset = so + start + len(encode(values)) - 4
        if result[gpu_offset:gpu_offset + 4] != bytes(4):
            raise ValueError("Rim GPU default offset")
        result[gpu_offset:gpu_offset + 4] = value
    elif (so, ss) != (0xFFFFFFFF, 0):
        raise ValueError("Expected shaderless filled child")
    if template(result[mo:mo + ms])["reflection"] != rows:
        raise ValueError("Liquid material reflection changed")
    return bytes(result)


def particle_variant(base, name, materials, clouds):
    changed = bytearray(base)
    original_id, = struct.unpack_from("<Q", base, 8)
    if original_id == murmur64(name):
        raise ValueError("Variant particle identity collision")
    struct.pack_into("<Q", changed, 8, murmur64(name))
    for row in clouds:
        old = "content/fx/materials/rainbow_barrels/liquid_" + row["stock_material"]
        offset = row["material_offset"]
        if struct.unpack_from("<Q", changed, offset)[0] != murmur64(old):
            raise ValueError("Original billboard binding changed")
        struct.pack_into("<Q", changed, offset, materials[row["stock_material"]])
    return bytes(changed)


def main():
    if OUT.exists():
        raise ValueError("Output already exists")
    report = json.loads((BASE / "report.json").read_text())
    original = (BASE / "bundle" / PACKAGE).read_bytes()
    if sha(original) != BASE_SHA or report["candidate_bundle_sha256"] != BASE_SHA:
        raise ValueError("Pinned accepted liquid bundle")
    parsed, padding = decode_bundle_parts(original, lambda block: block)
    if len(parsed) != 110 or any(padding):
        raise ValueError("Original 103 stock and 7 custom resource records")
    index = [identity for identity, _, _ in parsed]
    records = [raw for _, raw, _ in parsed]
    occupied = {identity[:2] for identity in index}
    assets = {item["identity"].rsplit("_", 1)[-1]: item for item in report["added_assets"]
              if item["kind"] == "material"}
    particles = {item["identity"].rsplit("/", 1)[-1]: item for item in report["added_assets"]
                 if item["kind"] == "particle"}
    bases = {}
    for name in CHILDREN | {RIM}:
        asset = assets[name]
        payload = (BASE / asset["stream"]).read_bytes()
        if sha(payload) != asset["sha256"]:
            raise ValueError("Pinned child/rim material source")
        bases[name] = payload
    base_particles = {}
    for stem in STEMS.values():
        item = particles[stem]
        data = next(raw for identity, raw, _ in parsed if identity[:2] ==
                    (murmur64("particles"), murmur64(item["identity"])))
        if sha(data) != item["sha256"]:
            raise ValueError("Pinned liquid particle source")
        base_particles[stem] = data
    streams = []
    generated = []
    output_streams = {}
    for hue in range(360):
        materials = {}
        for name in sorted(bases):
            path = f"content/fx/materials/rainbow_barrels/liquid_{name}_hue_{hue:03d}"
            key = murmur64(path)
            identity = murmur64("material"), key, 4
            relative = f"bundle/data/rb/{key:016x}"
            if identity[:2] in occupied or relative in output_streams:
                raise ValueError("Unique ground hue material identity")
            occupied.add(identity[:2])
            payload = material_variant(bases[name], hue, name == RIM)
            if hue == 120 and name in CHILDREN:
                row = next(item for item in json.loads((GREEN / "report.json").read_text())["changes"]
                           if item["identity"].endswith(name))
                if sha(payload) != row["green_sha256"]:
                    raise ValueError("Tested green child byte identity")
            if hue == 240 and name in CHILDREN:
                row = next(item for item in json.loads((BLUE / "report.json").read_text())["changed"]
                           if item["identity"].endswith(name))
                if sha(payload) != row["blue_sha256"]:
                    raise ValueError("Tested blue child byte identity")
            output_streams[relative] = payload
            materials[name] = key
            index.append(identity)
            records.append(resource_record(identity[0], key, f"data/rb/{key:016x}".encode() + bytes(4), True))
            streams.append({"name": path, "hue": hue, "stream": relative,
                            "bytes": len(payload), "sha256": sha(payload)})
        for label, stem in STEMS.items():
            path = f"content/fx/particles/rainbow_barrels/{stem}_hue_{hue:03d}"
            identity = murmur64("particles"), murmur64(path), 0
            if identity[:2] in occupied:
                raise ValueError("Unique ground hue particle identity")
            occupied.add(identity[:2])
            raw = particle_variant(base_particles[stem], path, materials, particles[stem]["clouds"])
            index.append(identity)
            records.append(raw)
            generated.append({"name": path, "hue": hue, "kind": label,
                              "bytes": len(raw), "sha256": sha(raw)})
    if len(index) != 1910 or len(output_streams) != 1080 or len(generated) != 720:
        raise ValueError("Incomplete 360-degree ground hue wheel")
    candidate = bundle(index, records, original[12:268])
    reread, tail = decode_bundle_parts(candidate, lambda block: block)
    if (len(reread) != len(index) or reread[:110] != parsed
            or [identity for identity, _, _ in reread] != index
            or [raw for _, raw, _ in reread] != records or any(tail)):
        raise ValueError("Complete liquid wheel resource roundtrip")
    OUT.mkdir(parents=True)
    destination = OUT / "bundle" / PACKAGE
    destination.parent.mkdir(parents=True)
    destination.write_bytes(candidate)
    for relative, payload in output_streams.items():
        dest = OUT / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
    summary = {"build": "24735202", "base_bundle_sha256": BASE_SHA,
               "candidate_bundle_sha256": sha(candidate), "candidate_bundle_bytes": len(candidate),
               "base_resources": len(parsed), "candidate_resources": len(reread),
               "added_material_streams": streams, "generated_particles": generated,
               "status": "offline candidate; deployment and arbitrary-hue ground behavior untested"}
    (OUT / "report.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: summary[key] for key in ("base_bundle_sha256", "candidate_bundle_sha256",
                                                 "candidate_bundle_bytes", "base_resources",
                                                 "candidate_resources", "status")}, indent=2))


if __name__ == "__main__":
    main()
