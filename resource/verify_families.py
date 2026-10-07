"""Independent whole-material readback of seven offline hue candidates."""

import hashlib
import json
from pathlib import Path
import struct

from author_material_families import MATERIALS, PARENTS, OUT, SHADERS, HASH32
from probe_defaults import defaults
from profile_exports import groups, template
from profile_shaders import inventory


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inspect(data):
    version, mo, ms, so, ss, other, other_size = struct.unpack_from("<7I", data)
    if version != 61 or mo != 28 or so != mo + ms or so + ss > len(data):
        raise ValueError("Material section bounds")
    if other != 0xFFFFFFFF and (other != so + ss or other + other_size != len(data)):
        raise ValueError("Material following section")
    shader = data[so:so + ss]
    header = struct.unpack_from("<12I", shader)
    start, size, device, device_size = header[8:12]
    if header[0] != 43 or not 48 <= start < start + size <= device < device + device_size <= header[5] <= len(shader):
        raise ValueError("Shader43 bounds")
    return template(data[mo:so]), groups(shader[start:start + size]), defaults(shader[header[5]:]), inventory(data)


def main():
    provenance = json.loads((OUT / "provenance.json").read_text())["materials"]
    if len(provenance) != 7:
        raise ValueError("Material count")
    source = {}
    for directory, rows, name, file, digest in (
        (MATERIALS, "materials", "identity", "material_file", "source_sha256"),
        (PARENTS, "parents", "parent", "extracted_file", "sha256"),
    ):
        for row in json.loads((directory / "provenance.json").read_text())[rows]:
            source[row[name]] = (directory / row[file], row[digest])
    shaders = json.loads((SHADERS / "provenance.json").read_text())["programs"]
    mappings = {}
    for row in shaders:
        mappings.setdefault(row["program"].split("-", 1)[0], {})[row["source_sha256"]] = row["authored_sha256"]
    results = []
    for report in provenance:
        name = report["material"]
        original_path, expected = source[name]
        raw = original_path.read_bytes()
        authored = (OUT / (name + ".material")).read_bytes()
        if sha(raw) != expected or sha(raw) != report["source_sha256"] or sha(authored) != report["candidate_sha256"]:
            raise ValueError("Stock/authored identity: " + name)
        old_mat, old_groups, old_defaults, old_frames = inspect(raw)
        new_mat, new_groups, new_defaults, new_frames = inspect(authored)
        if (len(new_mat["reflection"]) != len(old_mat["reflection"]) + 1
                or new_mat["reflection"][:-1] != old_mat["reflection"]
                or new_mat["reflection"][-1][2] != HASH32
                or new_mat["values_size"] != old_mat["values_size"] + 4):
            raise ValueError("Material export delta: " + name)
        if (new_defaults[:-1] != old_defaults or len(new_defaults) != len(old_defaults) + 1
                or new_defaults[-1] != (HASH32, struct.pack("<f", 0))):
            raise ValueError("Default export delta: " + name)
        if len(old_groups) != len(new_groups):
            raise ValueError("Registration group count: " + name)
        for before, after in zip(old_groups, new_groups):
            if any(before[key] != after[key] for key in ("key", "allocation", "resources", "associations", "techniques", "trailer")):
                raise ValueError("Unrelated group data changed: " + name)
            old_buffers, new_buffers = before["buffers"], after["buffers"]
            if len(old_buffers) != len(new_buffers) or any(
                a["size"] != b["size"] or a["offset"] != b["offset"]
                for a, b in zip(old_buffers, new_buffers)):
                raise ValueError("Buffer sizes/offsets changed: " + name)
            growth = sum(b["descriptors"] - a["descriptors"] for a, b in zip(old_buffers, new_buffers))
            if growth not in (0, 1):
                raise ValueError("Registration descriptor delta: " + name)
        if len(old_frames) != len(new_frames):
            raise ValueError("Shader program count: " + name)
        changes = []
        for index, (before, after) in enumerate(zip(old_frames, new_frames)):
            expected_program = mappings.get(name, {}).get(before["dxbc_sha256"], before["dxbc_sha256"])
            if after["dxbc_sha256"] != expected_program:
                raise ValueError("Unexpected shader program delta: " + name)
            if expected_program != before["dxbc_sha256"]:
                changes.append(index)
        if len(changes) != len(report["changed_programs"]):
            raise ValueError("Changed shader count: " + name)
        results.append({"material": name, "program_count": len(old_frames), "changed_pixel_programs": changes,
                        "registration_groups": len(old_groups), "candidate_sha256": sha(authored)})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
