"""Independent readback of full-buffer material growth and retained programs."""

import json
import struct

from author_full_materials import MATERIALS, PARENTS, OUT, PROFILES, SHADERS, HASH32, MATERIAL_BUFFER, sha
from profile_exports import Cursor
from verify_families import inspect


def metadata_sizes(data, frames):
    _, _, _, so, ss, _, _ = struct.unpack_from("<7I", data)
    shader = data[so:so + ss]
    sizes = []
    for program in frames:
        position = program["offset"]
        frame_size, = struct.unpack_from("<I", shader, position - 4)
        c = Cursor(shader)
        c.pos = position + frame_size
        if c.words()[0] != 5:
            raise ValueError("Program metadata kind")
        c.words(3)
        rows = c.table(6)
        matches = [row[2] for row in rows if row[0] == MATERIAL_BUFFER]
        if len(matches) > 1:
            raise ValueError("Duplicate program material binding")
        sizes.append(matches[0] if matches else None)
    return sizes


def main():
    reports = json.loads((OUT / "provenance.json").read_text())["materials"]
    if {row["material"] for row in reports} != set(PROFILES):
        raise ValueError("Material set")
    stock = {}
    for path, section, identity, filename, digest in (
        (MATERIALS, "materials", "identity", "material_file", "source_sha256"),
        (PARENTS, "parents", "parent", "extracted_file", "sha256"),
    ):
        for row in json.loads((path / "provenance.json").read_text())[section]:
            stock[row[identity]] = path / row[filename], row[digest]
    shaders = json.loads((SHADERS / "provenance.json").read_text())["programs"]
    mappings = {}
    for row in shaders:
        mappings.setdefault(row["program"].split("-", 1)[0], {})[row["source_sha256"]] = row["authored_sha256"]
    result = []
    for report in reports:
        name = report["material"]
        original_path, digest = stock[name]
        original = original_path.read_bytes()
        candidate = (OUT / (name + ".material")).read_bytes()
        if sha(original) != digest or sha(original) != report["source_sha256"] or sha(candidate) != report["candidate_sha256"]:
            raise ValueError("Material source/output identities")
        old_mat, old_groups, old_defaults, old_frames = inspect(original)
        new_mat, new_groups, new_defaults, new_frames = inspect(candidate)
        size_old, size_new = PROFILES[name][1:]
        if (new_mat["reflection"][:-1] != old_mat["reflection"]
                or new_mat["reflection"][-1][2] != HASH32
                or new_mat["values_size"] != old_mat["values_size"] + 4
                or new_defaults[:-1] != old_defaults
                or new_defaults[-1] != (HASH32, struct.pack("<f", 0))):
            raise ValueError("Material template/default delta")
        changed_groups = 0
        shifted = 0
        for before, after in zip(old_groups, new_groups):
            if any(before[key] != after[key] for key in ("key", "resources", "associations", "techniques", "trailer")):
                raise ValueError("Unrelated group data modified")
            if len(before["buffers"]) != len(after["buffers"]):
                raise ValueError("Material buffers count")
            targets = [i for i, (a, b) in enumerate(zip(before["buffers"], after["buffers"]))
                       if b["descriptors"] == a["descriptors"] + 1]
            if targets:
                if targets != [3] or before["buffers"][3]["size"] != size_old or after["buffers"][3]["size"] != size_new:
                    raise ValueError("Unexpected expanded buffer")
                if after["allocation"] != before["allocation"] + 16:
                    raise ValueError("Group allocation delta")
                changed_groups += 1
            elif before["allocation"] != after["allocation"]:
                raise ValueError("Untargeted allocation delta")
            for i, (a, b) in enumerate(zip(before["buffers"], after["buffers"])):
                if i != 3 and a["size"] != b["size"]:
                    raise ValueError("Other buffer size changed")
                expected_offset = a["offset"] + (16 if targets and i > 3 else 0)
                if b["offset"] != expected_offset:
                    raise ValueError("Other buffer offset relocation")
                shifted += int(expected_offset != a["offset"])
        if changed_groups != report["registered_groups"] or shifted != report["shifted_buffers"]:
            raise ValueError("Registration report mismatch")
        if len(old_frames) != len(new_frames) or len(old_frames) != report["source_programs"]:
            raise ValueError("Program count")
        changed = []
        for i, (a, b) in enumerate(zip(old_frames, new_frames)):
            expected = mappings[name].get(a["dxbc_sha256"], a["dxbc_sha256"])
            if b["dxbc_sha256"] != expected:
                raise ValueError("Unexpected shader frame replacement")
            if expected != a["dxbc_sha256"]:
                changed.append(i)
        if changed != [entry[0] for entry in report["changed_programs"]]:
            raise ValueError("Shader change positions")
        before_sizes, after_sizes = metadata_sizes(original, old_frames), metadata_sizes(candidate, new_frames)
        modified_rows = 0
        for old_size, new_size in zip(before_sizes, after_sizes):
            if old_size is None:
                if new_size is not None:
                    raise ValueError("Unbound material metadata mutated")
            elif old_size != size_old or new_size != size_new:
                raise ValueError("Bound material metadata size")
            else:
                modified_rows += 1
        if modified_rows != report["updated_metadata_rows"]:
            raise ValueError("Material program metadata count")
        result.append({"material": name, "changed_pixel_programs": len(changed),
                       "registration_groups": changed_groups, "shifted_buffers": shifted,
                       "metadata_rows": modified_rows, "sha256": sha(candidate)})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
