"""Extract only two stock particle records for offline barrel-effect research."""

import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys

from inspect_stock import EFFECTS, GAME, MAGICS, murmur64


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1] / "analysis" / "stock-particles-24735202"
SOURCES = (
    ("bundle/d2b0b18252164f5b", (EFFECTS[0],)),
    ("bundle/98bb14b1d247a0c8", EFFECTS),
)
CHUNK = 0x80000
OODLE_SHA256 = "8595a4795f1e0c7f548598f3e2aa528b6be5456c6d934c665182eaecb04156c0"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decoder():
    path = GAME / "binaries/oo2core_9_win64.dll"
    if sha(path.read_bytes()) != OODLE_SHA256:
        raise ValueError("Oodle decoder has changed")
    lib = ctypes.CDLL(str(path))
    memory = lib.OodleLZDecoder_MemorySizeNeeded
    memory.argtypes, memory.restype = [ctypes.c_int32, ctypes.c_int64], ctypes.c_uint64
    size = memory(-1, -1)
    if not 0 < size <= 16 * 1024 * 1024:
        raise ValueError("Decoder scratch bound")
    scratch = ctypes.create_string_buffer(size)
    decompress = lib.OodleLZ_Decompress
    decompress.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64,
                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                           ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_void_p, ctypes.c_uint64, ctypes.c_int]
    decompress.restype = ctypes.c_uint64

    def unpack(block):
        if len(block) == CHUNK:
            return block
        source = ctypes.create_string_buffer(block)
        output = ctypes.create_string_buffer(CHUNK)
        actual = decompress(source, len(block), output, CHUNK, 1, 0, 3,
                            None, 0, None, None, scratch, size, 3)
        if actual != CHUNK:
            raise ValueError("Decoded block size")
        return output.raw
    return unpack


def decode_bundle_parts(data, unpack):
    if not 0 < len(data) < 64 * 1024 * 1024 or data[:8] not in MAGICS:
        raise ValueError("Unexpected source bundle format or size")
    count, = struct.unpack_from("<I", data, 8)
    if not 1 <= count <= 2048:
        raise ValueError("Unexpected resource count")
    offset = 268
    index = list(struct.iter_unpack("<QQI", data[offset:offset + count * 20]))
    if len(index) != count:
        raise ValueError("Truncated index")
    offset += count * 20
    chunks, = struct.unpack_from("<I", data, offset)
    if not 1 <= chunks <= 64:
        raise ValueError("Chunk bound")
    offset += 4
    sizes = struct.unpack_from("<" + "I" * chunks, data, offset)
    if any(not 0 < size <= CHUNK for size in sizes):
        raise ValueError("Chunk size bound")
    offset += chunks * 4
    offset += (-offset) % 16
    length, reserved = struct.unpack_from("<II", data, offset)
    offset += 8
    if reserved or not 0 < length <= chunks * CHUNK or (length + CHUNK - 1) // CHUNK != chunks:
        raise ValueError("Logical stream length")
    blocks = []
    for size in sizes:
        actual, = struct.unpack_from("<I", data, offset)
        offset += 4
        offset += (-offset) % 16
        if actual != size or offset + size > len(data):
            raise ValueError("Inline chunk size")
        blocks.append(unpack(data[offset:offset + size]))
        offset += size
    if offset != len(data):
        raise ValueError("Trailing bundle bytes")
    complete = b"".join(blocks)
    stream = complete[:length]
    cursor = 0
    records = []
    for identity in index:
        start = cursor
        kind, name, variants, zero = struct.unpack_from("<QQII", stream, cursor)
        cursor += 24
        if (kind, name) != identity[:2] or zero or not 1 <= variants <= 64:
            raise ValueError("Resource/index identity")
        descriptors = []
        for _ in range(variants):
            descriptor = struct.unpack_from("<IBIBI", stream, cursor)
            cursor += 14
            if descriptor[1] not in (0, 1) or descriptor[3] != 1:
                raise ValueError("Variant flags")
            descriptors.append(descriptor)
        for _, _, body, _, tail in descriptors:
            cursor += body + tail
            if cursor > len(stream):
                raise ValueError("Variant boundary")
        records.append((identity, stream[start:cursor], descriptors))
    if cursor != len(stream):
        raise ValueError("Unconsumed logical bytes")
    return records, complete[length:]


def decode_bundle(data, unpack):
    return decode_bundle_parts(data, unpack)[0]


def main():
    if OUT.exists():
        raise ValueError("Research directory already exists; use a new analysis location")
    manifest = json.loads((ROOT / "mods/active/RainbowFlame/payload/manifest.json").read_text())
    managed = {item["target"].lower() for item in manifest["files"]}
    vortex = json.loads((GAME / "vortex.deployment.json").read_text())
    deployed = {item["relPath"].replace("\\", "/").lower() for item in vortex["files"]}
    unpack = decoder()
    extracted = []
    for relative, effects in SOURCES:
        if relative.lower() in managed or relative.lower() in deployed:
            raise ValueError(f"Known installed replacement: {relative}")
        source = GAME / relative
        data = source.read_bytes()
        records = decode_bundle(data, unpack)
        for name in effects:
            target = (murmur64("particles"), murmur64(name))
            matches = [(index, raw, descriptors, identity[2])
                       for index, (identity, raw, descriptors) in enumerate(records)
                       if identity[:2] == target]
            if len(matches) != 1:
                raise ValueError(f"Particle identity count: {name}")
            index, raw, descriptors, mode = matches[0]
            extracted.append((relative, name, data, index, raw, descriptors, mode))
    OUT.mkdir(parents=True)
    evidence = []
    for relative, name, data, index, raw, descriptors, mode in extracted:
        filename = f"{Path(relative).name}-{Path(name).name}.particles"
        (OUT / filename).write_bytes(raw)
        evidence.append({"effect": name, "game_source": str(GAME / relative),
                         "source_size": len(data), "source_sha256": sha(data),
                         "resource_index": index, "mode": mode,
                         "variant_descriptors": descriptors, "extracted_file": filename,
                         "extracted_size": len(raw), "extracted_sha256": sha(raw)})
    report = {"steam_build": "24735202", "exe_version": "1.3.770.210",
              "stock_check": "not listed in RainbowFlame payload or Vortex deployment; Steam build matches",
              "status": "offline research; no installed writes", "particles": evidence}
    (OUT / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
