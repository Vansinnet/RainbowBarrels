"""Offline cloned lingering-fire particles and five material registrations."""

import hashlib
import json
from pathlib import Path
import struct

from analyze_effects import GAME, decode_bundle_parts, decoder
from build_green_bundle import bundle, resource_record, sha
from inspect_stock import murmur64
from profile_particles import profile


ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "analysis/liquid-stock-24735202"
SHADERS = ROOT / "analysis/liquid-hue-materials-24735202"
EXISTING = ROOT / "analysis/hue-wheel-bundle-24735202"
OUT = ROOT / "analysis/liquid-bundle-trial-24735202"
PACKAGE = "b224998193576995"
PACKAGE_SHA = "775762aae54cfd5313856f8b097e2527774600e92df896d375e4af6b8916376d"
PARENT = {"d11c8f091a39ef54": "1cc58f33452ca960",
          "62b838cfa247b2ca": "62c7bb3aa1cac9c2"}
NAMES = {"fire_lingering": ("content/fx/particles/rainbow_barrels/fire_lingering_filled", "ground_filled"),
         "fire_lingering_edge": ("content/fx/particles/rainbow_barrels/fire_lingering_rim", "ground_edge")}


def material_sources():
    catalog = {row["material"]: row for row in json.loads((SHADERS / "provenance.json").read_text())["materials"]}
    original = {row["identity"]: row for row in json.loads((STOCK / "materials-provenance.json").read_text())["materials"]}
    result = {}
    for name in set(catalog) | set(PARENT):
        if name in catalog:
            path = SHADERS / (name + ".material")
            payload = path.read_bytes()
            if sha(payload) != catalog[name]["candidate_sha256"]:
                raise ValueError("Compiled liquid material identity drift")
        else:
            row = original[name]
            source = (STOCK / "materials" / row["retained_file"]).read_bytes()
            if sha(source) != row["stream_sha256"] or struct.unpack_from("<Q", source, 32)[0] != int(PARENT[name], 16):
                raise ValueError("Stock child material parent")
            rewritten = bytearray(source)
            custom_parent = murmur64("content/fx/materials/rainbow_barrels/liquid_" + PARENT[name])
            struct.pack_into("<Q", rewritten, 32, custom_parent)
            restored = bytearray(rewritten)
            struct.pack_into("<Q", restored, 32, int(PARENT[name], 16))
            if restored != source:
                raise ValueError("Child material-only parent rewrite")
            payload = bytes(rewritten)
        result[name] = payload
    if len(result) != 5:
        raise ValueError("Three shader parents plus two material children required")
    return result


def particle(source, effect, custom, cloud_prefix, materials):
    before = profile(source)
    rewritten = bytearray(source)
    changed = []
    for row in before["clouds"]:
        if row["visualizer_type"] != 0:
            continue
        old_material = row["material_candidate"]
        if old_material not in materials:
            raise ValueError("Unmapped liquid billboard material")
        offset = 38 + row["visualizer_offset"] + 12
        if struct.unpack_from("<Q", rewritten, offset)[0] != int(old_material, 16):
            raise ValueError("Particle material reference position")
        custom_material = murmur64("content/fx/materials/rainbow_barrels/liquid_" + old_material)
        struct.pack_into("<Q", rewritten, offset, custom_material)
        cloud_name = "RainbowBarrels_" + cloud_prefix + f"_{row['index']:02d}"
        cloud_id = murmur64(cloud_name) >> 32
        start = 38 + row["body_offset"]
        if struct.unpack_from("<I", rewritten, start)[0] != int(row["cloud_id32"], 16):
            raise ValueError("Liquid particle cloud identity position")
        if any(existing["cloud_id32"] == f"{cloud_id:08x}" for existing in before["clouds"]):
            raise ValueError("Cloned liquid cloud identity collision")
        struct.pack_into("<I", rewritten, start, cloud_id)
        changed.append({"cloud": row["index"], "name": cloud_name,
                        "stock_material": old_material, "material_offset": offset,
                        "cloud_offset": start, "old_cloud_id": row["cloud_id32"]})
    if struct.unpack_from("<Q", rewritten, 8)[0] != murmur64(effect):
        raise ValueError("Stock liquid particle identity")
    struct.pack_into("<Q", rewritten, 8, murmur64(custom))
    back = bytearray(rewritten)
    struct.pack_into("<Q", back, 8, murmur64(effect))
    for row in changed:
        struct.pack_into("<Q", back, row["material_offset"], int(row["stock_material"], 16))
        struct.pack_into("<I", back, row["cloud_offset"], int(row["old_cloud_id"], 16))
    if back != source:
        raise ValueError("Liquid particle-only identity/material delta")
    return bytes(rewritten), changed


def main():
    if OUT.exists():
        raise ValueError("Research output already exists")
    source = GAME / "bundle" / PACKAGE
    stock = source.read_bytes()
    if sha(stock) != PACKAGE_SHA:
        raise ValueError("Original liquid package changed")
    if stock[:8] != bytes.fromhex("080000f003000000"):
        raise ValueError("Liquid bundle is not the supported stock format-8 encoding")
    records, tail = decode_bundle_parts(stock, decoder())
    if len(records) != 103 or any(tail):
        raise ValueError("Original liquid package/padding")
    index = [identity for identity, _, _ in records]
    resources = [raw for _, raw, _ in records]
    no_op = bundle(index, resources, stock[12:268], tail)
    checked, _ = decode_bundle_parts(no_op, lambda block: block)
    if checked != records:
        raise ValueError("Physical no-op logical reconstruction")
    originals = {row["effect"]: row for row in json.loads((STOCK / "provenance.json").read_text())["particles"]
                 if PACKAGE in row["bundle"]}
    existing_streams = {row["path"] for row in json.loads((EXISTING / "report.json").read_text())["added_material_streams"]}
    occupied = {entry[:2] for entry in index}
    additions, description = {}, []
    materials = material_sources()
    for old, payload in sorted(materials.items()):
        path = "content/fx/materials/rainbow_barrels/liquid_" + old
        key = murmur64(path)
        ident = (murmur64("material"), key, 4)
        relative = f"bundle/data/rb/{key:016x}"
        if ident[:2] in occupied or relative in existing_streams:
            raise ValueError("Generated liquid material collision with game/explosion")
        occupied.add(ident[:2])
        additions[relative] = payload
        index.append(ident)
        resources.append(resource_record(ident[0], key, f"data/rb/{key:016x}".encode("ascii") + bytes(4), True))
        description.append({"kind": "material", "identity": path, "stream": relative,
                            "sha256": sha(payload), "bytes": len(payload)})
    for effect, original in originals.items():
        stem = Path(effect).name
        custom, name = NAMES[stem]
        raw = next(raw for identity, raw, _ in records if identity[:2] == (murmur64("particles"), murmur64(effect)))
        if sha(raw) != original["record_sha256"]:
            raise ValueError("Original liquid particle record changed")
        edited, clouds = particle(raw, effect, custom, name, materials)
        identity = (murmur64("particles"), murmur64(custom), 0)
        if identity[:2] in occupied:
            raise ValueError("Generated liquid particle collision")
        occupied.add(identity[:2])
        index.append(identity)
        resources.append(edited)
        description.append({"kind": "particle", "identity": custom, "sha256": sha(edited),
                            "bytes": len(edited), "clouds": clouds})
    if len(additions) != 5 or len(index) != 110 or len(description) != 7:
        raise ValueError("Incomplete liquid bundle candidate")
    candidate = bundle(index, resources, stock[12:268])
    parsed, padding = decode_bundle_parts(candidate, lambda block: block)
    if [key for key, _, _ in parsed] != index or [raw for _, raw, _ in parsed] != resources or any(padding):
        raise ValueError("Expanded liquid package readback")
    OUT.mkdir(parents=True)
    (OUT / "bundle").mkdir()
    (OUT / "bundle" / PACKAGE).write_bytes(candidate)
    (OUT / "bundle/data").mkdir()
    (OUT / "bundle/data/rb").mkdir()
    for path, data in additions.items():
        (OUT / path).write_bytes(data)
    report = {"build": "24735202", "source_bundle_sha256": sha(stock),
              "noop_bundle_sha256": sha(no_op), "candidate_bundle_sha256": sha(candidate),
              "candidate_bundle_bytes": len(candidate), "stock_resources": len(records),
              "candidate_resources": len(parsed), "added_assets": description,
              "status": "offline stock-preserving liquid-fire candidate; not installed or game-tested"}
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("source_bundle_sha256", "noop_bundle_sha256",
                                                  "candidate_bundle_sha256", "candidate_bundle_bytes",
                                                  "stock_resources", "candidate_resources", "status")}, indent=2))


if __name__ == "__main__":
    main()
