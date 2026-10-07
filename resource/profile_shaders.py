"""Read-only shader-frame inventory of the stock explosion materials."""

import hashlib
import importlib
import json
from pathlib import Path
import struct
import sys


ROOT = Path(__file__).resolve().parents[4]
MATERIALS = Path(__file__).resolve().parents[1] / "analysis" / "stock-materials-24735202"
PARENTS = Path(__file__).resolve().parents[1] / "analysis" / "stock-parents-24735202"
sys.path.insert(0, str(ROOT / "docs/analysis-flame-shader43-20260918-j1"))
sys.path.insert(0, str(ROOT / "docs/analysis-flame-huecycle-build-20260918-o1"))
shader = importlib.import_module("decode")
old = importlib.import_module("investigate")


def inventory(data, include_code=False):
    _, mo, ms, so, ss, tail, ts = struct.unpack_from("<7I", data)
    if ss == 0:
        return []
    if so + ss > len(data):
        raise ValueError("Material section bounds")
    wrapped = data[so:so + ss]
    header = struct.unpack_from("<12I", wrapped)
    start, size = header[10:12]
    end = start + size
    if header[0] != 43 or not 48 <= start < end <= header[5] <= len(wrapped):
        raise ValueError("Shader device bounds")
    frames = []
    cursor = start
    while (begin := wrapped.find(b"\x8c\x06", cursor, end)) != -1:
        cursor = begin + 2
        if begin < start + 8 or begin + 5 >= end:
            continue
        envelope, length = struct.unpack_from("<II", wrapped, begin - 8)
        finish = begin + length
        if envelope != 1 or not begin + 8 <= finish <= end - 16:
            continue
        frame = wrapped[begin:finish]
        if int.from_bytes(frame[2:5], "big") + 1 != len(frame) - 5:
            continue
        kind, decoded_size, key = struct.unpack_from("<IIQ", wrapped, finish)
        if kind != 5 or not 32 <= decoded_size <= 262144 or old.murmur64(frame) != key:
            continue
        decoded = shader.decompress(frame, decoded_size)
        if decoded[:4] != b"DXBC" or len(decoded) < 40:
            raise ValueError("Decoded program is not a DXBC container")
        count, = struct.unpack_from("<I", decoded, 28)
        if not 1 <= count <= 16 or 32 + 4 * count > len(decoded):
            raise ValueError("DXBC chunk directory")
        stages = set()
        for i in range(count):
            offset, = struct.unpack_from("<I", decoded, 32 + 4 * i)
            if offset + 12 > len(decoded):
                raise ValueError("DXBC chunk bounds")
            size, = struct.unpack_from("<I", decoded, offset + 4)
            if offset + 8 + size > len(decoded):
                raise ValueError("DXBC chunk size")
            if decoded[offset:offset + 4] == b"DXIL":
                version, = struct.unpack_from("<I", decoded, offset + 8)
                stages.add(version >> 16)
        if len(stages) != 1:
            raise ValueError("DXIL stage count")
        record = {"offset": begin, "stage": next(iter(stages)),
                  "dxbc_sha256": hashlib.sha256(decoded).hexdigest()}
        if include_code:
            record["dxbc"] = decoded
        frames.append(record)
        cursor = finish
    return frames


def main():
    records = json.loads((MATERIALS / "provenance.json").read_text())["materials"]
    result = []
    for item in records:
        data = (MATERIALS / item["material_file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["source_sha256"]:
            raise ValueError("Material evidence drift")
        try:
            frames = inventory(data)
        except ValueError as error:
            raise ValueError(f"{item['identity']}: {error}") from error
        stages = {stage: sum(row["stage"] == stage for row in frames)
                  for stage in sorted({row["stage"] for row in frames})}
        result.append({"identity": item["identity"], "shader_size": item["shader_size"],
                       "programs": len(frames), "stages": stages,
                       "unique_pixel_programs": len({row["dxbc_sha256"] for row in frames
                                                     if row["stage"] == 0})})
    for item in json.loads((PARENTS / "provenance.json").read_text())["parents"]:
        data = (PARENTS / item["extracted_file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Parent material evidence drift")
        frames = inventory(data)
        stages = {stage: sum(row["stage"] == stage for row in frames)
                  for stage in sorted({row["stage"] for row in frames})}
        result.append({"identity": item["parent"], "shader_size": item["shader_size"],
                       "programs": len(frames), "stages": stages,
                       "unique_pixel_programs": len({row["dxbc_sha256"] for row in frames
                                                     if row["stage"] == 0})})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
