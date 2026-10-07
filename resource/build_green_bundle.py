"""Build one isolated green explosion variant per barrel; offline candidate only."""

import hashlib
import json
import math
from pathlib import Path
import struct

from analyze_effects import GAME, SOURCES, decode_bundle_parts, decoder
from author_light_graphs import TARGETS as LIGHT_PROFILES, author as author_lights
from inspect_stock import murmur64
from profile_particles import HERE, profile


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis/green-bundle-trial-24735202"
SHADER_MATERIALS = (ROOT / "analysis/hue-material-families-24735202",
                    ROOT / "analysis/hue-full-materials-24735202")
CHILDREN = {"5108fe05ccddb30c": "debe1ef92005d87e",
            "71e7d6426e8b2c65": "e14900c258cc9b8e",
            "f338e336d436c97b": "84dce57f22a9d409"}
PARTICLES = murmur64("particles")
MATERIAL = murmur64("material")
CHUNK = 0x80000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def resource_record(kind, name, body, streamed):
    if len(body) > 10_000_000:
        raise ValueError("Generated resource bound")
    flag = 1 if streamed else 0
    return (struct.pack("<QQII", kind, name, 1, 0)
            + struct.pack("<IBIBI", 0, flag, len(body), 1, 0) + body)


def bundle(index, records, opaque, original_padding=None):
    if len(index) != len(records) or len({row[:2] for row in index}) != len(index):
        raise ValueError("Bundle index and resource identities")
    logical = b"".join(records)
    count = math.ceil(len(logical) / CHUNK)
    if not 1 <= count <= 64:
        raise ValueError("Bounded bundle chunk count")
    padding = bytes(count * CHUNK - len(logical))
    if original_padding is not None:
        if len(original_padding) != len(padding):
            raise ValueError("No-op padding extent")
        padding = original_padding
    payload = logical + padding
    result = bytearray(struct.pack("<QI", int.from_bytes(bytes.fromhex("080000f003000000"), "little"), len(index)))
    result += opaque
    for identity in index:
        result += struct.pack("<QQI", *identity)
    result += struct.pack("<I", count)
    result += struct.pack("<" + "I" * count, *([CHUNK] * count))
    result += bytes((-len(result)) % 16)
    result += struct.pack("<II", len(logical), 0)
    for i in range(count):
        result += struct.pack("<I", CHUNK)
        result += bytes((-len(result)) % 16)
        result += payload[i * CHUNK:(i + 1) * CHUNK]
    return bytes(result)


def material_sources():
    inputs = {}
    for path in SHADER_MATERIALS:
        manifest = json.loads((path / "provenance.json").read_text())
        for item in manifest["materials"]:
            key = item["material"]
            data = (path / (key + ".material")).read_bytes()
            if sha(data) != item["candidate_sha256"] or key in inputs:
                raise ValueError("Authored material identity/collision")
            inputs[key] = data
    for path, section, identity, filename, digest in (
        (ROOT / "analysis/stock-materials-24735202", "materials", "identity", "material_file", "source_sha256"),
        (ROOT / "analysis/stock-parents-24735202", "parents", "parent", "extracted_file", "sha256"),
    ):
        for item in json.loads((path / "provenance.json").read_text())[section]:
            key = item[identity]
            if key not in CHILDREN:
                continue
            source = (path / item[filename]).read_bytes()
            if sha(source) != item[digest] or struct.unpack_from("<Q", source, 32)[0] != int(CHILDREN[key], 16):
                raise ValueError("Stock child material reference")
            changed = bytearray(source)
            struct.pack_into("<Q", changed, 32, murmur64("content/fx/materials/rainbow_barrels/" + CHILDREN[key]))
            restored = bytearray(changed)
            struct.pack_into("<Q", restored, 32, int(CHILDREN[key], 16))
            if restored != source:
                raise ValueError("Child material-only reference delta")
            inputs[key] = bytes(changed)
    if len(inputs) != 13:
        raise ValueError("Ten shader materials and three child references required")
    return inputs


def particle(effect, source, label, materials, hue):
    original = profile(source)
    name = "content/fx/particles/rainbow_barrels/" + label + f"_hue_{hue:03d}"
    modified, lights = author_lights(source, hue, LIGHT_PROFILES[effect.split("/")[-1]])
    after = bytearray(modified)
    cloud_names = []
    material_changes = []
    for row in original["clouds"]:
        if row["visualizer_type"] != 0 or not row["material_candidate"]:
            continue
        old = row["material_candidate"]
        if old not in materials:
            raise ValueError("Unresolved billboard material identity: " + old)
        new_material = murmur64("content/fx/materials/rainbow_barrels/" + old)
        offset = 38 + row["visualizer_offset"] + 12
        if struct.unpack_from("<Q", after, offset)[0] != int(old, 16):
            raise ValueError("Exact stock particle material field")
        struct.pack_into("<Q", after, offset, new_material)
        material_changes.append((offset, old))
        cloud = f"RainbowBarrels_{label}_{row['index']:02d}"
        cloud_hash = murmur64(cloud) >> 32
        if cloud_hash in (int(existing["cloud_id32"], 16) for existing in original["clouds"]):
            raise ValueError("Cloud identifier collision")
        start = 38 + row["body_offset"]
        if struct.unpack_from("<I", after, start)[0] != int(row["cloud_id32"], 16):
            raise ValueError("Exact stock cloud identifier field")
        struct.pack_into("<I", after, start, cloud_hash)
        cloud_names.append((row["index"], cloud, start, row["cloud_id32"]))
    old_name = struct.unpack_from("<Q", after, 8)[0]
    if old_name != murmur64(effect):
        raise ValueError("Source particle identity changed")
    struct.pack_into("<Q", after, 8, murmur64(name))
    restored = bytearray(after)
    struct.pack_into("<Q", restored, 8, old_name)
    for index, cloud, start, old_hash in cloud_names:
        struct.pack_into("<I", restored, start, int(old_hash, 16))
    for offset, old in material_changes:
        struct.pack_into("<Q", restored, offset, int(old, 16))
    if bytes(restored) != modified:
        raise ValueError("Only named clouds/material references rewritten")
    if not cloud_names or not lights:
        raise ValueError("Incomplete particle display graph")
    return name, bytes(after), {"effect": effect, "name": name,
                                "light_keys": len(lights),
                                "billboard_cloud_names": [cloud for _, cloud, _, _ in cloud_names]}


def main():
    if OUT.exists():
        raise ValueError("Output exists; use a fresh candidate directory")
    source = GAME / SOURCES[1][0]
    data = source.read_bytes()
    evidence = json.loads((HERE / "provenance.json").read_text())["particles"]
    expected = next(item["source_sha256"] for item in evidence if item["game_source"] == str(source))
    if sha(data) != expected:
        raise ValueError("Stock game bundle identity")
    entries, padding = decode_bundle_parts(data, decoder())
    if len(entries) != 423 or any(padding):
        raise ValueError("Stock bundle profile/padding")
    original_index = [identity for identity, _, _ in entries]
    original_records = [raw for _, raw, _ in entries]
    opaque = data[12:268]
    noop = bundle(original_index, original_records, opaque, padding)
    noop_entries, noop_padding = decode_bundle_parts(noop, lambda block: block)
    if noop_entries != entries or noop_padding != padding:
        raise ValueError("No-op stored bundle logical roundtrip")
    indexed = set(entry[:2] for entry in original_index)
    generated = set()
    artifacts = {}
    additions = []
    report = []
    materials = material_sources()
    for old, stream in sorted(materials.items()):
        name = "content/fx/materials/rainbow_barrels/" + old
        identity = MATERIAL, murmur64(name), 4
        if identity[:2] in indexed | generated:
            raise ValueError("Material identity collision")
        generated.add(identity[:2])
        relative = f"bundle/data/rb/{identity[1]:016x}"
        pointer = relative[7:].encode("ascii") + bytes(4)
        record = resource_record(identity[0], identity[1], pointer, True)
        artifacts[relative] = stream
        additions.append((identity, record))
        report.append({"kind": "material", "identity": name, "stream": relative,
                       "sha256": sha(stream), "bytes": len(stream)})
    profiles = (("frag_grenade_01", "explosive"), ("explosive_barrel_explosion", "fire"))
    for basename, label in profiles:
        item = next(e for e in evidence if e["game_source"] == str(source) and e["effect"].endswith(basename))
        raw = next(raw for identity, raw, _ in entries if identity[:2] == (PARTICLES, murmur64(item["effect"])))
        if sha(raw) != item["extracted_sha256"]:
            raise ValueError("Stock particle record drift")
        name, rewritten, details = particle(item["effect"], raw, label, materials, 120)
        identity = PARTICLES, murmur64(name), 0
        if identity[:2] in indexed | generated:
            raise ValueError("Particle identity collision")
        generated.add(identity[:2])
        additions.append((identity, rewritten))
        details["sha256"] = sha(rewritten)
        report.append(details)
    if len(additions) != 15:
        raise ValueError("Generated record set")
    index = original_index + [identity for identity, _ in additions]
    records = original_records + [raw for _, raw in additions]
    candidate = bundle(index, records, opaque)
    reread, tail = decode_bundle_parts(candidate, lambda block: block)
    if ([identity for identity, _, _ in reread] != index
            or [raw for _, raw, _ in reread[:len(entries)]] != original_records
            or [raw for _, raw, _ in reread[len(entries):]] != [raw for _, raw in additions]
            or any(tail)):
        raise ValueError("Whole package original preservation and generated readback")
    OUT.mkdir(parents=True)
    (OUT / "bundle").mkdir()
    (OUT / "bundle/98bb14b1d247a0c8").write_bytes(candidate)
    (OUT / "bundle/data").mkdir()
    (OUT / "bundle/data/rb").mkdir()
    for relative, stream in artifacts.items():
        (OUT / relative).write_bytes(stream)
    summary = {"game_build": "24735202", "stock_bundle_sha256": sha(data),
               "stored_noop_sha256": sha(noop), "candidate_sha256": sha(candidate),
               "candidate_bytes": len(candidate), "stock_records": len(entries),
               "candidate_records": len(reread), "added_assets": report,
               "status": "offline green candidate; not installed or accepted by game"}
    (OUT / "report.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: summary[key] for key in ("stock_bundle_sha256", "candidate_sha256",
                                                  "candidate_bytes", "stock_records", "candidate_records", "status")}, indent=2))


if __name__ == "__main__":
    main()
