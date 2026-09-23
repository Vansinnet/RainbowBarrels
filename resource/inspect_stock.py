"""Read-only identification of two stock barrel explosion particle bundles."""

import hashlib
import json
import os
from pathlib import Path
import struct


GAME = Path(r"D:\Steam\steamapps\common\Warhammer 40,000 DARKTIDE")
EFFECTS = (
    "content/fx/particles/explosions/frag_grenade_01",
    "content/fx/particles/destructibles/explosive_barrel_explosion",
)
MAGICS = {bytes.fromhex("080000f003000000"), bytes.fromhex("070000f003000000")}


def murmur64(text):
    data = text.encode()
    multiplier = 0xc6a4a7935bd1e995
    mask = (1 << 64) - 1
    value = len(data) * multiplier & mask
    end = len(data) // 8 * 8
    for (word,) in struct.iter_unpack("<Q", data[:end]):
        word = word * multiplier & mask
        word ^= word >> 47
        value = (value ^ (word * multiplier & mask)) * multiplier & mask
    if data[end:]:
        value = (value ^ int.from_bytes(data[end:], "little")) * multiplier & mask
    value ^= value >> 47
    value = value * multiplier & mask
    return value ^ (value >> 47)


def inspect(name):
    path = GAME / "bundle" / f"{murmur64(name):016x}"
    if not path.is_file():
        return {"effect": name, "path": str(path), "present": False}
    with path.open("rb") as source:
        header = source.read(12)
        if len(header) != 12 or header[:8] not in MAGICS:
            raise ValueError(f"Unknown bundle format: {path}")
        count, = struct.unpack_from("<I", header, 8)
        if not 1 <= count <= 1_000_000:
            raise ValueError(f"Unexpected index count: {path}")
        source.seek(256, 1)
        index = source.read(20 * count)
        if len(index) != 20 * count:
            raise ValueError(f"Short index: {path}")
        matches = [i for i in range(count)
                   if struct.unpack_from("<QQ", index, 20 * i)
                   == (murmur64("particles"), murmur64(name))]
        source.seek(0)
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"effect": name, "path": str(path), "present": True,
            "bytes": path.stat().st_size, "sha256": digest, "resources": count,
            "particle_index": matches}


def locate(effects=EFFECTS):
    identities = {murmur64(name): name for name in effects}
    matches = []
    inspected = 0
    for entry in os.scandir(GAME / "bundle"):
        if len(entry.name) != 16 or not all(c in "0123456789abcdef" for c in entry.name):
            continue
        if not entry.is_file(follow_symlinks=False):
            continue
        inspected += 1
        with open(entry.path, "rb") as source:
            header = source.read(12)
            if len(header) != 12 or header[:8] not in MAGICS:
                continue
            count, = struct.unpack_from("<I", header, 8)
            if not 1 <= count <= 1_000_000:
                continue
            source.seek(256, 1)
            index = source.read(20 * count)
            if len(index) != 20 * count:
                continue
            for i in range(count):
                kind, name = struct.unpack_from("<QQ", index, 20 * i)
                if kind == murmur64("particles") and name in identities:
                    source.seek(0)
                    matches.append({"effect": identities[name], "path": entry.path,
                                    "particle_index": i, "resources": count,
                                    "bytes": entry.stat().st_size,
                                    "sha256": hashlib.file_digest(source, "sha256").hexdigest()})
    return {"indexed_bundles_checked": inspected, "matches": matches}


if __name__ == "__main__":
    assert murmur64("lua") == 0xA14E8DFA2CD117E2, f"lua={murmur64('lua'):016x}"
    assert murmur64("material") == 0xEAC0B497876ADEDF, f"material={murmur64('material'):016x}"
    print(json.dumps({"standalone": [inspect(name) for name in EFFECTS],
                      "indexed": locate()}, indent=2))
