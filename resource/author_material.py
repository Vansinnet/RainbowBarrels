"""Author a single scoped barrel material hue export; offline candidate only."""

import hashlib
import json
from pathlib import Path
import struct

from experiment_hue import EXPORT_NAME, OUT as HUE, STOCK_SHA
from probe_defaults import defaults, encode
from probe_layout import PATH, PROVENANCE
from profile_exports import Cursor, pack_table, pack_words
from profile_shaders import inventory, old, shader as codec


OUT = Path(__file__).resolve().parents[1] / "analysis" / "hue-material-trial-24735202"
HASH32 = old.murmur64(EXPORT_NAME.encode()) >> 32
STOCK_MATERIAL_SHA = "5232ffc199ec0e11cb80558ed8604fa09bfb411c56a299d46640724ed5d64ebd"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def material_template(data, append):
    c = Cursor(data)
    head = c.take(20)
    tables = [c.table(width) for width in (1, 3, 2, 5)]
    values = c.take(c.words()[0])
    trailing_count, = c.words()
    trailing = c.take(trailing_count * 5)
    last = c.table(2)
    if c.pos != len(data):
        raise ValueError("Material template exhaustion")
    original = (head + b"".join(pack_table(t) for t in tables)
                + pack_words((len(values),)) + values + pack_words((trailing_count,))
                + trailing + pack_table(last))
    if original != data:
        raise ValueError("Material template identity roundtrip")
    if append:
        if len(values) != 20 or len(tables[3]) != 3 or any(t[2] == HASH32 for t in tables[3]):
            raise ValueError("Exact material exports profile")
        tables[3].append((0, 0, HASH32, len(values), 4))
        values += struct.pack("<f", 0)
    return (head + b"".join(pack_table(t) for t in tables)
            + pack_words((len(values),)) + values + pack_words((trailing_count,))
            + trailing + pack_table(last))


def shader_groups(data, append):
    c = Cursor(data)
    count, = c.words()
    if count != 3:
        raise ValueError("Shader group profile")
    pieces = [pack_words((count,))]
    changes = 0
    for _ in range(count):
        key, allocation = c.words(2)
        resources = c.table(4)
        buffers_count, = c.words()
        if buffers_count != 3 or len(resources) != 6 or allocation != 288:
            raise ValueError("Shader group registration profile")
        part = pack_words((key, allocation)) + pack_table(resources) + pack_words((buffers_count,))
        for _ in range(buffers_count):
            rows = c.table(5)
            size, offset = c.words(2)
            if size == 64 and offset == 224 and len(rows) == 8:
                if append:
                    if any(row[2] == HASH32 for row in rows):
                        raise ValueError("Existing custom shader export")
                    rows.append((0, 0, HASH32, 52, 4))
                    changes += 1
            part += pack_table(rows) + pack_words((size, offset))
        associations = c.table(7)
        technique_count, = c.words()
        if technique_count != 1 or len(associations) != 6:
            raise ValueError("Shader technique profile")
        opaque = c.take(17 * technique_count)
        trailer = c.take(8)
        part += pack_table(associations) + pack_words((technique_count,)) + opaque + trailer
        pieces.append(part)
    result = b"".join(pieces)
    if c.pos != len(data) or (not append and result != data) or (append and changes != 3):
        raise ValueError("Shader groups roundtrip/export count")
    return result


def metadata_end(shader, end):
    c = Cursor(shader)
    c.pos = end
    header = c.words(4)
    if header[0] != 5:
        raise ValueError("Program metadata header")
    for width in (6, 0, 0, 7, 7, 7, 7, 4, 3, 3):
        c.table(width)
    return c.pos


def device_data(shader, begin, length, replacement):
    end = begin + length
    cursor = begin
    pieces = []
    count = 0
    previous = begin
    while (frame := shader.find(b"\x8c\x06", cursor, end)) != -1:
        cursor = frame + 2
        if frame < begin + 8 or frame + 5 >= end:
            continue
        envelope, encoded = struct.unpack_from("<II", shader, frame - 8)
        finish = frame + encoded
        if envelope != 1 or finish > end - 16:
            continue
        payload = shader[frame:finish]
        if payload[:2] != b"\x8c\x06" or int.from_bytes(payload[2:5], "big") + 1 != len(payload) - 5:
            continue
        kind, decoded_length, frame_key = struct.unpack_from("<IIQ", shader, finish)
        if kind != 5 or old.murmur64(payload) != frame_key:
            continue
        stop = metadata_end(shader, finish)
        decoded = codec.decompress(payload, decoded_length)
        if decoded[:4] != b"DXBC":
            raise ValueError("Shader program signature")
        stage = None
        directories, = struct.unpack_from("<I", decoded, 28)
        for i in range(directories):
            offset, = struct.unpack_from("<I", decoded, 32 + i * 4)
            if decoded[offset:offset + 4] == b"DXIL":
                version, = struct.unpack_from("<I", decoded, offset + 8)
                stage = version >> 16
        pieces.append(shader[previous:frame - 8])
        metadata = bytearray(shader[finish:stop])
        if stage == 0 and replacement is not None:
            if sha(decoded) != STOCK_SHA:
                raise ValueError("Unexpected color program")
            payload = b"\x8c\x06" + (len(replacement) - 1).to_bytes(3, "big") + replacement
            struct.pack_into("<IQ", metadata, 4, len(replacement), old.murmur64(payload))
        pieces.extend((struct.pack("<II", 1, len(payload)), payload, bytes(metadata)))
        previous = stop
        cursor = stop
        count += 1
    if count != 6:
        raise ValueError("Exact shader program count")
    pieces.append(shader[previous:end])
    rebuilt = b"".join(pieces)
    if replacement is None and rebuilt != shader[begin:end]:
        raise ValueError("Device identity roundtrip")
    return rebuilt


def author(source, altered, replacement):
    version, mo, ms, so, ss, other, other_size = struct.unpack_from("<7I", source)
    if version != 61 or mo != 28 or so != mo + ms or other != 0xFFFFFFFF or other_size != 0:
        raise ValueError("Exact stock material envelope")
    material = material_template(source[mo:so], altered)
    shader = source[so:so + ss]
    header = struct.unpack_from("<12I", shader)
    start, group_size, device, device_size = header[8:12]
    original_defaults = header[5]
    if header[0] != 43 or not 48 <= start < start + group_size <= device < device + device_size <= original_defaults <= len(shader):
        raise ValueError("Shader43 section bounds")
    groups = shader_groups(shader[start:start + group_size], altered)
    stock_defaults = defaults(shader[original_defaults:])
    if altered:
        if any(key == HASH32 for key, _ in stock_defaults):
            raise ValueError("Existing custom default")
        stock_defaults.append((HASH32, struct.pack("<f", 0)))
    new_device = device_data(shader, device, device_size, replacement)
    gap = shader[start + group_size:device]
    if any(gap) or len(gap) != (-start - len(groups)) % 4:
        raise ValueError("Unknown group/device alignment")
    new_device_start = start + len(groups) + len(gap)
    new_defaults_start = (new_device_start + len(new_device) + 3) & ~3
    prefix = bytearray(shader[:start])
    struct.pack_into("<I", prefix, 20, new_defaults_start)
    struct.pack_into("<I", prefix, 36, len(groups))
    struct.pack_into("<II", prefix, 40, new_device_start, len(new_device))
    new_shader = (bytes(prefix) + groups + gap + new_device
                  + bytes(new_defaults_start - new_device_start - len(new_device))
                  + encode(stock_defaults))
    new_shader += bytes((-len(new_shader)) % 16)
    wrapper = bytearray(source[:28])
    struct.pack_into("<III", wrapper, 8, len(material), 28 + len(material), len(new_shader))
    candidate = bytes(wrapper) + material + new_shader + source[so + ss:]
    if not altered and candidate != source:
        differences = [i for i, (a, b) in enumerate(zip(source, candidate)) if a != b]
        raise ValueError(f"Whole-material no-op reconstruction: lengths {len(source)}, {len(candidate)}; first differences {differences[:16]}")
    return candidate


def main():
    if OUT.exists():
        raise ValueError("Output exists; choose a fresh analysis path")
    source = PATH.read_bytes()
    if sha(source) != STOCK_MATERIAL_SHA:
        raise ValueError("Stock material identity changed")
    evidence = json.loads(PROVENANCE.read_text())
    if not any(row["identity"] == PATH.stem and row["source_sha256"] == STOCK_MATERIAL_SHA
               for row in evidence["materials"]):
        raise ValueError("Missing material provenance")
    replacement = (HUE / "candidate.dxbc").read_bytes()
    result = json.loads((HUE / "report.json").read_text())
    if sha(replacement) != result["candidate_sha256"]:
        raise ValueError("Authored shader identity")
    author(source, False, None)
    candidate = author(source, True, replacement)
    OUT.mkdir(parents=True)
    (OUT / "hue.material").write_bytes(candidate)
    report = {"source_sha256": sha(source), "candidate_sha256": sha(candidate),
              "candidate_bytes": len(candidate), "no_op_identity": True,
              "status": "offline candidate; native loader and runtime tint untested"}
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
