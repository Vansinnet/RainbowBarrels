"""Bounded read-only stock material dependency chain for lingering fire and rim."""

import hashlib
import json
from pathlib import Path
import re
import struct

from analyze_effects import GAME, decode_bundle_parts, decoder
from inspect_stock import murmur64
from profile_particles import profile


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis/liquid-stock-24735202"
PACKAGE = "b224998193576995"
SOURCE_SHA = "775762aae54cfd5313856f8b097e2527774600e92df896d375e4af6b8916376d"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def resolve():
    path = GAME / "bundle" / PACKAGE
    package = path.read_bytes()
    if sha(package) != SOURCE_SHA:
        raise ValueError("Liquid package identity drift")
    records, _ = decode_bundle_parts(package, decoder())
    provenance = json.loads((OUT / "provenance.json").read_text())
    pending = set()
    for item in provenance["particles"]:
        if PACKAGE not in item["bundle"]:
            continue
        particle = (OUT / item["file"]).read_bytes()
        if sha(particle) != item["record_sha256"]:
            raise ValueError("Liquid particle changed")
        pending.update(row["material_candidate"] for row in profile(particle)["clouds"]
                       if row["visualizer_type"] == 0 and row["material_candidate"])
    managed = {item["target"].lower(): item for item in json.loads(
        (ROOT.parent / "RainbowFlame/payload/manifest.json").read_text())["files"]}
    result = []
    visited = set()
    while pending:
        if len(visited) > 16:
            raise ValueError("Unexpected liquid material graph depth")
        identity = pending.pop()
        if identity in visited:
            continue
        visited.add(identity)
        matches = [(i, raw, key[2]) for i, (key, raw, _) in enumerate(records)
                   if key[:2] == (murmur64("material"), int(identity, 16))]
        if len(matches) != 1:
            result.append({"identity": identity, "record_matches": len(matches), "in_small_package": False})
            continue
        index, raw, mode = matches[0]
        references = re.findall(rb"data/[0-9a-f]{2}/[0-9a-f]{16}", raw)
        if len(references) != 1 or mode != 4:
            raise ValueError("Liquid material stream record profile")
        relative = "bundle/" + references[0].decode()
        stream = (GAME / relative).read_bytes()
        _, mo, ms, so, ss, other, ts = struct.unpack_from("<7I", stream)
        if mo != 28 or mo + ms > len(stream) or (ss and so + ss > len(stream)):
            raise ValueError(f"Liquid material section boundary: {identity}, {relative}, {(mo, ms, so, ss, len(stream))}")
        parents = [f"{p:016x}" for p in struct.unpack_from("<QQ", stream, mo + 4)
                   if p != 0]
        pending.update(parents)
        owner = managed.get(relative)
        status = ("verified stock" if owner and sha(stream) == owner["baseSha256"]
                  else "RainbowFlame replacement" if owner and sha(stream) == owner["outputSha256"]
                  else "unexpected managed file" if owner else "not managed by RainbowFlame")
        result.append({"identity": identity, "resource_index": index,
                       "record_sha256": sha(raw), "stream": str(GAME / relative),
                       "stream_bytes": len(stream), "stream_sha256": sha(stream),
                       "status": status, "parents": parents, "shader_bytes": ss})
    return result


if __name__ == "__main__":
    print(json.dumps(resolve(), indent=2))
