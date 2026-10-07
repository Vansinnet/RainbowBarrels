"""Build scoped scalar-hue candidates for the three full-buffer material profiles."""

import hashlib
import json
from pathlib import Path
import struct

from author_material import HASH32, metadata_end
from author_material_families import MATERIALS, PARENTS, SHADERS, material_template, sha
from probe_defaults import defaults, encode
from profile_exports import Cursor, groups as inspect_groups, pack_table, pack_words
from profile_shaders import inventory, old, shader as codec


OUT = Path(__file__).resolve().parents[1] / "analysis" / "hue-full-materials-24735202"
ANCHOR_HASH = 0x2CC3DCEE
MATERIAL_BUFFER = old.murmur64(b"c_material_exports") >> 32
PROFILES = {
    "be9333164c3ddf4a": (12, 80, 96),
    "debe1ef92005d87e": (16, 80, 96),
    "e14900c258cc9b8e": (19, 128, 144),
}


def registration(data, name, expand):
    inspect_groups(data)
    c = Cursor(data)
    count, = c.words()
    expected_count, old_size, new_size = PROFILES[name]
    if count != expected_count or new_size != old_size + 16:
        raise ValueError("Exact full-buffer group profile")
    result = pack_words((count,))
    expanded = 0
    shifted = 0
    for _ in range(count):
        key, allocation = c.words(2)
        resources = c.table(4)
        n, = c.words()
        buffers = []
        for _ in range(n):
            rows = c.table(5)
            size, offset = c.words(2)
            buffers.append((rows, size, offset))
        target = [i for i, (rows, _, _) in enumerate(buffers)
                  if any(row[2] == ANCHOR_HASH for row in rows)]
        if len(target) > 1:
            raise ValueError("Duplicate material buffer")
        if target:
            index = target[0]
            rows, size, offset = buffers[index]
            used = max(row[3] + max(1, row[1]) * row[4] for row in rows)
            if (index != 3 or size != old_size or used != old_size
                    or any(row[2] == HASH32 for row in rows)):
                raise ValueError("Exact scalar export buffer")
            if allocation != max(other_offset + other_size for _, other_size, other_offset in buffers
                                 if other_offset > 0 and other_size < 1024):
                raise ValueError("Buffer allocation extent")
            if expand:
                rows.append((0, 0, HASH32, old_size, 4))
                buffers[index] = (rows, new_size, offset)
                boundary = offset + old_size
                for j in range(index + 1, len(buffers)):
                    later, later_size, later_offset = buffers[j]
                    if later_offset < boundary:
                        raise ValueError("Unmapped buffer relocation")
                    buffers[j] = (later, later_size, later_offset + 16)
                    shifted += 1
                allocation += 16
                expanded += 1
        part = pack_words((key, allocation)) + pack_table(resources) + pack_words((n,))
        for rows, size, offset in buffers:
            if any(row[3] + max(1, row[1]) * row[4] > size for row in rows):
                raise ValueError("Buffer descriptor extent")
            part += pack_table(rows) + pack_words((size, offset))
        associations = c.table(7)
        techniques, = c.words()
        if techniques > 64:
            raise ValueError("Technique count")
        part += pack_table(associations) + pack_words((techniques,)) + c.take(17 * techniques + 8)
        result += part
    if c.pos != len(data) or (not expand and result != data) or (expand and expanded < 1):
        raise ValueError("Registration identity/expanded group count")
    inspect_groups(result)
    return result, expanded, shifted


def rewrite_device(shader, begin, size, replacements, old_buffer_size, new_buffer_size):
    end = begin + size
    previous = begin
    pieces = []
    count = 0
    changed = []
    metadata_changes = 0
    position = begin
    while (frame := shader.find(b"\x8c\x06", position, end)) != -1:
        position = frame + 2
        if frame < begin + 8 or frame + 5 > end:
            continue
        envelope, encoded = struct.unpack_from("<II", shader, frame - 8)
        finish = frame + encoded
        if envelope != 1 or finish > end - 16:
            continue
        payload = shader[frame:finish]
        if int.from_bytes(payload[2:5], "big") + 1 != len(payload) - 5:
            continue
        kind, decoded_size, frame_key = struct.unpack_from("<IIQ", shader, finish)
        if kind != 5 or frame_key != old.murmur64(payload):
            continue
        stop = metadata_end(shader, finish)
        decoded = codec.decompress(payload, decoded_size)
        key = sha(decoded)
        metadata = bytearray(shader[finish:stop])
        replacement = replacements.get(key)
        if replacement is not None:
            if not 32 <= len(replacement) <= 262143:
                raise ValueError("DXBC single-frame bound")
            payload = b"\x8c\x06" + (len(replacement) - 1).to_bytes(3, "big") + replacement
            struct.pack_into("<IQ", metadata, 4, len(replacement), old.murmur64(payload))
            changed.append((count, key, sha(replacement)))
        if new_buffer_size != old_buffer_size:
            table_count, = struct.unpack_from("<I", metadata, 16)
            for row in range(table_count):
                position_in_metadata = 20 + row * 24
                name, _, size_field = struct.unpack_from("<III", metadata, position_in_metadata)
                if name == MATERIAL_BUFFER:
                    if size_field != old_buffer_size:
                        raise ValueError("Material program metadata size")
                    struct.pack_into("<I", metadata, position_in_metadata + 8, new_buffer_size)
                    metadata_changes += 1
            if replacement is not None and not any(struct.unpack_from("<I", metadata, 20 + row * 24)[0] == MATERIAL_BUFFER
                                                   for row in range(table_count)):
                raise ValueError("Hue shader missing registered material metadata")
        pieces.extend((shader[previous:frame - 8], pack_words((1, len(payload))), payload, bytes(metadata)))
        previous = stop
        position = stop
        count += 1
    pieces.append(shader[previous:end])
    result = b"".join(pieces)
    if not replacements and old_buffer_size == new_buffer_size and result != shader[begin:end]:
        raise ValueError("Whole-device no-op roundtrip")
    return result, count, changed, metadata_changes


def author(source, name, replacements):
    version, mo, ms, so, ss, other, other_size = struct.unpack_from("<7I", source)
    if version != 61 or mo != 28 or so != mo + ms or so + ss > len(source):
        raise ValueError("Material61 bounds")
    if other != 0xFFFFFFFF and (other != so + ss or other + other_size != len(source)):
        raise ValueError("Material following-section bounds")
    shader = source[so:so + ss]
    fields = struct.unpack_from("<12I", shader)
    start, group_size, device_start, device_size = fields[8:12]
    default_start = fields[5]
    if fields[0] != 43 or not 48 <= start < start + group_size <= device_start < device_start + device_size <= default_start <= len(shader):
        raise ValueError("Shader43 section boundaries")
    material_template(source[mo:so], False)
    registration(shader[start:start + group_size], name, False)
    defaults(shader[default_start:])
    stock_device, count, _, _ = rewrite_device(shader, device_start, device_size, {}, PROFILES[name][1], PROFILES[name][1])
    if stock_device != shader[device_start:device_start + device_size] or count != len(inventory(source)):
        raise ValueError("Program no-op inventory")
    material = material_template(source[mo:so], True)
    groups, changed_groups, shifted = registration(shader[start:start + group_size], name, True)
    default_values = defaults(shader[default_start:])
    if any(key == HASH32 for key, _ in default_values):
        raise ValueError("Existing custom shader default")
    default_values.append((HASH32, struct.pack("<f", 0)))
    rebuilt_device, actual, changed, metadata_rows = rewrite_device(shader, device_start, device_size,
                                                                     replacements, PROFILES[name][1], PROFILES[name][2])
    if actual != count or not changed or metadata_rows < len(changed):
        raise ValueError("Incomplete shader/metadata authoring")
    old_gap = shader[start + group_size:device_start]
    if any(old_gap) or len(old_gap) > 3:
        raise ValueError("Unmapped shader group alignment")
    new_device_start = start + len(groups) + (-start - len(groups)) % 4
    new_default_start = (new_device_start + len(rebuilt_device) + 3) & ~3
    header = bytearray(shader[:start])
    struct.pack_into("<I", header, 20, new_default_start)
    struct.pack_into("<I", header, 36, len(groups))
    struct.pack_into("<II", header, 40, new_device_start, len(rebuilt_device))
    new_shader = (bytes(header) + groups + bytes(new_device_start - start - len(groups)) + rebuilt_device
                  + bytes(new_default_start - new_device_start - len(rebuilt_device)) + encode(default_values))
    new_shader += bytes((-len(new_shader)) % 16)
    wrapper = bytearray(source[:28])
    struct.pack_into("<III", wrapper, 8, len(material), 28 + len(material), len(new_shader))
    if other != 0xFFFFFFFF:
        struct.pack_into("<I", wrapper, 20, 28 + len(material) + len(new_shader))
    result = bytes(wrapper) + material + new_shader + source[so + ss:]
    return result, {"material": name, "source_sha256": sha(source), "candidate_sha256": sha(result),
                    "source_programs": count, "changed_programs": changed,
                    "registered_groups": changed_groups, "shifted_buffers": shifted,
                    "updated_metadata_rows": metadata_rows}


def main():
    if OUT.exists():
        raise ValueError("Research output already exists")
    stock = {}
    for path, section, identity, filename, digest in (
        (MATERIALS, "materials", "identity", "material_file", "source_sha256"),
        (PARENTS, "parents", "parent", "extracted_file", "sha256"),
    ):
        for row in json.loads((path / "provenance.json").read_text())[section]:
            stock[row[identity]] = (path / row[filename], row[digest])
    programs = json.loads((SHADERS / "provenance.json").read_text())["programs"]
    result, files = [], {}
    for name in PROFILES:
        path, expected = stock[name]
        source = path.read_bytes()
        if sha(source) != expected:
            raise ValueError("Stock source SHA-256 drift")
        replacements = {}
        rows = [item for item in programs if item["program"].startswith(name + "-")]
        if not rows or len({row["export_offset"] for row in rows}) != 1 or rows[0]["export_offset"] != PROFILES[name][1]:
            raise ValueError("Exact shader reflection/buffer profile")
        for item in rows:
            payload = (SHADERS / (item["program"] + ".dxbc")).read_bytes()
            if sha(payload) != item["authored_sha256"]:
                raise ValueError("Authored pixel SHA-256 drift")
            previous = replacements.setdefault(item["source_sha256"], payload)
            if previous != payload:
                raise ValueError("Conflicting shader replacement identity")
        candidate, report = author(source, name, replacements)
        files[name + ".material"] = candidate
        result.append(report)
    OUT.mkdir(parents=True)
    for name, data in files.items():
        (OUT / name).write_bytes(data)
    (OUT / "provenance.json").write_text(json.dumps({"build": "24735202",
                                                  "status": "offline candidates; unregistered and untested in game",
                                                  "materials": result}, indent=2) + "\n")
    print(json.dumps([{"material": row["material"], "changed_programs": len(row["changed_programs"]),
                      "registered_groups": row["registered_groups"],
                      "shifted_buffers": row["shifted_buffers"],
                      "updated_metadata_rows": row["updated_metadata_rows"],
                      "candidate_sha256": row["candidate_sha256"]} for row in result], indent=2))


if __name__ == "__main__":
    main()
