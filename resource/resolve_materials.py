"""Locate only material references used by the two profiled explosion particles."""

import hashlib
import json
from pathlib import Path
import re
import struct

from analyze_effects import GAME, OUT, SOURCES, decode_bundle, decoder
from inspect_stock import murmur64
from profile_particles import profile

ROOT = Path(__file__).resolve().parents[4]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def resolve():
    evidence = json.loads((OUT / "provenance.json").read_text())
    installed = json.loads((ROOT / "mods/active/RainbowFlame/payload/manifest.json").read_text())
    managed = {item["target"].lower(): item for item in installed["files"]}
    for item in evidence["particles"]:
        if sha(Path(item["game_source"]).read_bytes()) != item["source_sha256"]:
            raise ValueError("Particle source changed since extraction")
    materials = {}
    for item in evidence["particles"]:
        data = (OUT / item["extracted_file"]).read_bytes()
        if sha(data) != item["extracted_sha256"]:
            raise ValueError("Particle identity changed")
        for row in profile(data)["clouds"]:
            if row["visualizer_type"] == 0 and row["material_candidate"]:
                key = row["material_candidate"]
                materials.setdefault(key, []).append({"effect": item["effect"],
                                                       "source": item["game_source"],
                                                       "cloud": row["index"]})
    source = GAME / SOURCES[1][0]
    records = decode_bundle(source.read_bytes(), decoder())
    results = []
    for hash_hex, consumers in sorted(materials.items()):
        matches = [(index, raw, identity[2]) for index, (identity, raw, _) in enumerate(records)
                   if identity[:2] == (murmur64("material"), int(hash_hex, 16))]
        paths = []
        for index, raw, mode in matches:
            for found in re.findall(rb"data/[0-9a-f]{2}/[0-9a-f]{16}", raw):
                path = GAME / "bundle" / found.decode()
                if path.is_file():
                    data = path.read_bytes()
                    relative = "bundle/" + found.decode()
                    item = managed.get(relative)
                    status = ("RainbowFlame replacement" if item and sha(data) == item["outputSha256"]
                              else "verified stock" if item and sha(data) == item["baseSha256"]
                              else "unexpected managed file" if item else "not managed by RainbowFlame")
                    entry = {"path": str(path), "bytes": len(data), "sha256": sha(data),
                             "installed_status": status}
                    if status in ("not managed by RainbowFlame", "verified stock"):
                        version, mo, ms, so, ss, tail, ts = struct.unpack_from("<7I", data)
                        entry["version"] = version
                        if version in (60, 61) and mo == 28 and so + ss <= len(data) and tail + ts <= len(data):
                            entry["parents"] = [f"{hash_value:016x}" for hash_value in
                                                struct.unpack_from("<QQ", data, mo + 4)]
                            entry["shader_size"] = ss
                    paths.append(entry)
            results.append({"material_hash": hash_hex, "consumers": consumers,
                            "resource_index": index, "resource_mode": mode,
                            "resource_bytes": len(raw), "resource_sha256": sha(raw),
                            "streams": paths})
        if not matches:
            results.append({"material_hash": hash_hex, "consumers": consumers,
                            "in_target_bundle": False})
    return results


if __name__ == "__main__":
    print(json.dumps(resolve(), indent=2))
