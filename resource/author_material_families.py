"""Offline authoring for exact stock barrel material profiles with spare scalar space."""

import hashlib
import json
from pathlib import Path
import struct

from author_material import HASH32, metadata_end
from probe_defaults import defaults, encode
from profile_exports import Cursor, pack_table, pack_words, groups as inspect_groups, template as inspect_template
from profile_shaders import inventory, old, shader as codec


ROOT = Path(__file__).resolve().parents[1]
MATERIALS = ROOT / "analysis/stock-materials-24735202"
PARENTS = ROOT / "analysis/stock-parents-24735202"
SHADERS = ROOT / "analysis/hue-pixel-programs-24735202"
OUT = ROOT / "analysis/hue-material-families-24735202"
TARGETS = {"082914d27a058793", "256482f981ddaf8c", "2e47bba2f141d42a",
           "362b6999973734bf", "9cda55b98bbfc8ff", "fa7e1d9d2de423bb",
           "84dce57f22a9d409"}
ANCHOR_HASH = 0x2CC3DCEE


def sha(data):
    return hashlib.sha256(data).hexdigest()


def material_template(data, append):
    original = inspect_template(data)
    c = Cursor(data)
    head = c.take(20)
    tables = [c.table(width) for width in (1, 3, 2, 5)]
    value = c.take(c.words()[0])
    count, = c.words()
    opaque = c.take(count * 5)
    last = c.table(2)
    if c.pos != len(data) or len(value) != original["values_size"]:
        raise ValueError("Material template structure")
    if append:
        if any(row[2] == HASH32 for row in tables[3]):
            raise ValueError("Export hash collision")
        tables[3].append((0, 0, HASH32, len(value), 4))
        value += struct.pack("<f", 0)
    result = (head + b"".join(pack_table(rows) for rows in tables)
              + pack_words((len(value),)) + value + pack_words((count,)) + opaque
              + pack_table(last))
    if not append and result != data:
        raise ValueError("Material template no-op roundtrip")
    return result


def registration(data, offset, append):
    inspect_groups(data)
    c = Cursor(data)
    count, = c.words()
    result = pack_words((count,))
    changed = 0
    for _ in range(count):
        key, allocation = c.words(2)
        resources = c.table(4)
        n, = c.words()
        part = pack_words((key, allocation)) + pack_table(resources) + pack_words((n,))
        for _ in range(n):
            descriptors = c.table(5)
            size, start = c.words(2)
            if any(row[2] == ANCHOR_HASH for row in descriptors):
                if not any(row[3] + row[4] == offset for row in descriptors):
                    raise ValueError("Material-buffer offset/reflection mismatch")
                if offset + 4 > size:
                    raise ValueError("Material GPU buffer full; requires a separate relocation profile")
                if append:
                    if any(row[2] == HASH32 for row in descriptors):
                        raise ValueError("Export identity collision")
                    descriptors.append((0, 0, HASH32, offset, 4))
                    changed += 1
            part += pack_table(descriptors) + pack_words((size, start))
        associations = c.table(7)
        techniques, = c.words()
        part += pack_table(associations) + pack_words((techniques,)) + c.take(17 * techniques + 8)
        result += part
    if c.pos != len(data) or (not append and result != data) or (append and changed < 1):
        raise ValueError("Shader registration no-op/change count")
    inspect_groups(result)
    return result, changed


def repack_device(shader, begin, size, replacements):
    end = begin + size
    previous = begin
    fragments = []
    found = 0
    changed = []
    position = begin
    while (frame := shader.find(b"\x8c\x06", position, end)) >= 0:
        position = frame + 2
        if frame < begin + 8 or frame + 5 > end:
            continue
        prefix, encoded = struct.unpack_from("<II", shader, frame - 8)
        stop_frame = frame + encoded
        if prefix != 1 or stop_frame > end - 16:
            continue
        old_frame = shader[frame:stop_frame]
        if int.from_bytes(old_frame[2:5], "big") + 1 != len(old_frame) - 5:
            continue
        kind, decoded_size, frame_hash = struct.unpack_from("<IIQ", shader, stop_frame)
        if kind != 5 or frame_hash != old.murmur64(old_frame):
            continue
        end_metadata = metadata_end(shader, stop_frame)
        program = codec.decompress(old_frame, decoded_size)
        original_sha = sha(program)
        metadata = bytearray(shader[stop_frame:end_metadata])
        payload = old_frame
        new = replacements.get(original_sha)
        if new is not None:
            if not 32 <= len(new) <= 262143:
                raise ValueError("Stored DXIL frame bound")
            payload = b"\x8c\x06" + (len(new) - 1).to_bytes(3, "big") + new
            struct.pack_into("<IQ", metadata, 4, len(new), old.murmur64(payload))
            changed.append((found, original_sha, sha(new)))
        fragments.extend((shader[previous:frame - 8], pack_words((1, len(payload))), payload, bytes(metadata)))
        previous = end_metadata
        position = end_metadata
        found += 1
    fragments.append(shader[previous:end])
    result = b"".join(fragments)
    if not replacements and result != shader[begin:end]:
        raise ValueError("Whole device-data no-op roundtrip")
    return result, found, changed


def author(source, name, offset, replacements):
    version, mo, ms, so, ss, other, other_size = struct.unpack_from("<7I", source)
    if version != 61 or mo != 28 or so != mo + ms or so + ss > len(source):
        raise ValueError("Stock material envelope")
    if other != 0xFFFFFFFF and (other != so + ss or other + other_size != len(source)):
        raise ValueError("Material tail offset")
    shader = source[so:so + ss]
    fields = struct.unpack_from("<12I", shader)
    start, group_size, device_start, device_size = fields[8:12]
    default_start = fields[5]
    if fields[0] != 43 or not 48 <= start < start + group_size <= device_start < device_start + device_size <= default_start <= len(shader):
        raise ValueError("Shader43 section bounds")
    material_template(source[mo:so], False)
    registration(shader[start:start + group_size], offset, False)
    defaults(shader[default_start:])
    old_device, program_count, _ = repack_device(shader, device_start, device_size, {})
    if program_count != len(inventory(source)) or old_device != shader[device_start:device_start + device_size]:
        raise ValueError("Program inventory disagreement")
    material = material_template(source[mo:so], True)
    groups, registration_count = registration(shader[start:start + group_size], offset, True)
    values = defaults(shader[default_start:])
    if any(key == HASH32 for key, _ in values):
        raise ValueError("Default export collision")
    values.append((HASH32, struct.pack("<f", 0)))
    new_device, count, changed = repack_device(shader, device_start, device_size, replacements)
    if count != program_count or not changed:
        raise ValueError("Expected color-program replacements")
    gap = shader[start + group_size:device_start]
    new_start = start + len(groups) + (-start - len(groups)) % 4
    if any(gap) or new_start < start + len(groups) or new_start - start - len(groups) > 3:
        raise ValueError("Opaque group/device alignment")
    new_default = (new_start + len(new_device) + 3) & ~3
    head = bytearray(shader[:start])
    struct.pack_into("<I", head, 20, new_default)
    struct.pack_into("<I", head, 36, len(groups))
    struct.pack_into("<II", head, 40, new_start, len(new_device))
    rebuilt = (bytes(head) + groups + bytes(new_start - start - len(groups)) + new_device
               + bytes(new_default - new_start - len(new_device)) + encode(values))
    rebuilt += bytes((-len(rebuilt)) % 16)
    outer = bytearray(source[:28])
    struct.pack_into("<III", outer, 8, len(material), 28 + len(material), len(rebuilt))
    if other != 0xFFFFFFFF:
        struct.pack_into("<I", outer, 20, 28 + len(material) + len(rebuilt))
    result = bytes(outer) + material + rebuilt + source[so + ss:]
    return result, {"material": name, "source_sha256": sha(source), "candidate_sha256": sha(result),
                    "source_programs": program_count, "changed_programs": changed,
                    "registered_groups": registration_count}


def main():
    if OUT.exists():
        raise ValueError("Output already exists")
    catalog = {}
    for path, section, identity, filekey, digest in (
        (MATERIALS, "materials", "identity", "material_file", "source_sha256"),
        (PARENTS, "parents", "parent", "extracted_file", "sha256"),
    ):
        for row in json.loads((path / "provenance.json").read_text())[section]:
            catalog[row[identity]] = (path / row[filekey], row[digest])
    programs = json.loads((SHADERS / "provenance.json").read_text())["programs"]
    payloads, reports = {}, []
    for name in sorted(TARGETS):
        source_file, expected = catalog[name]
        source = source_file.read_bytes()
        if sha(source) != expected:
            raise ValueError("Pinned source material drift")
        rows = [p for p in programs if p["program"].startswith(name + "-")]
        if not rows or len({p["export_offset"] for p in rows}) != 1:
            raise ValueError("Material shader/hue offset profile")
        offset = rows[0]["export_offset"]
        revisions = {}
        for row in rows:
            data = (SHADERS / (row["program"] + ".dxbc")).read_bytes()
            if sha(data) != row["authored_sha256"]:
                raise ValueError("Authored pixel source drift")
            old = revisions.setdefault(row["source_sha256"], data)
            if old != data:
                raise ValueError("Different compiled shaders for one source identity")
        candidate, report = author(source, name, offset, revisions)
        payloads[name + ".material"] = candidate
        reports.append(report)
    if len(reports) != len(TARGETS):
        raise ValueError("Incomplete material family build")
    OUT.mkdir(parents=True)
    for filename, data in payloads.items():
        (OUT / filename).write_bytes(data)
    (OUT / "provenance.json").write_text(json.dumps({"build": "24735202",
                                                  "status": "offline candidates; unregistered and untested in game",
                                                  "materials": reports}, indent=2) + "\n")
    print(json.dumps([{"material": r["material"], "changed_programs": len(r["changed_programs"]),
                      "registered_groups": r["registered_groups"],
                      "candidate_sha256": r["candidate_sha256"]} for r in reports], indent=2))


if __name__ == "__main__":
    main()
