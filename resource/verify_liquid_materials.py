"""Independent stock-versus-authored liquid-fire material readback."""

import json
from pathlib import Path
import struct

from author_material import HASH32
from verify_families import inspect
from verify_full_materials import metadata_sizes


ROOT = Path(__file__).resolve().parents[1] / "analysis"
STOCK = ROOT / "liquid-stock-24735202"
OUT = ROOT / "liquid-hue-materials-24735202"
SHADERS = ROOT / "liquid-hue-programs-24735202"


def main():
    originals = {row["identity"]: row for row in json.loads(
        (STOCK / "materials-provenance.json").read_text())["materials"]}
    reports = json.loads((OUT / "provenance.json").read_text())["materials"]
    programs = json.loads((SHADERS / "provenance.json").read_text())["programs"]
    lookup = {}
    for row in programs:
        lookup.setdefault(row["program"].split("-", 1)[0], {})[row["source_sha256"]] = row["authored_sha256"]
    verified = []
    for report in reports:
        name = report["material"]
        stock = originals[name]
        before = (STOCK / "materials" / stock["retained_file"]).read_bytes()
        after = (OUT / (name + ".material")).read_bytes()
        if report["source_sha256"] != stock["stream_sha256"]:
            raise ValueError("Material source provenance")
        import hashlib
        digest = lambda payload: hashlib.sha256(payload).hexdigest()
        if digest(before) != report["source_sha256"] or digest(after) != report["candidate_sha256"]:
            raise ValueError("Source/modified material hash")
        b_mat, b_groups, b_defaults, b_frames = inspect(before)
        a_mat, a_groups, a_defaults, a_frames = inspect(after)
        if (a_mat["reflection"][:-1] != b_mat["reflection"]
                or a_mat["reflection"][-1][2] != HASH32
                or a_mat["values_size"] != b_mat["values_size"] + 4
                or a_defaults[:-1] != b_defaults
                or a_defaults[-1] != (HASH32, struct.pack("<f", 0))):
            raise ValueError("Scalar export or defaults mismatch")
        if len(b_groups) != len(a_groups) or len(b_frames) != len(a_frames):
            raise ValueError("Group/program count changed")
        changed, registration = [], 0
        for i, (original, current) in enumerate(zip(b_frames, a_frames)):
            expected = lookup.get(name, {}).get(original["dxbc_sha256"], original["dxbc_sha256"])
            if current["dxbc_sha256"] != expected:
                raise ValueError("Unexpected shader program delta")
            if original["dxbc_sha256"] != expected:
                changed.append(i)
        for old_group, new_group in zip(b_groups, a_groups):
            if any(old_group[key] != new_group[key]
                   for key in ("key", "resources", "associations", "techniques", "trailer")):
                raise ValueError("Unrelated shader registration mutation")
            growth = sum(b["descriptors"] - a["descriptors"]
                         for a, b in zip(old_group["buffers"], new_group["buffers"]))
            if growth not in (0, 1):
                raise ValueError("Descriptor growth profile")
            registration += growth
            if name == "62c7bb3aa1cac9c2":
                expected_allocation = old_group["allocation"] + 16 * growth
                if new_group["allocation"] != expected_allocation:
                    raise ValueError("Parent material allocation relocation")
            elif new_group["allocation"] != old_group["allocation"]:
                raise ValueError("Unneeded material allocation relocation")
        if changed != [row[0] for row in report["changed_programs"]] or registration != report["registered_groups"]:
            raise ValueError("Modified shader/registration report mismatch")
        if name == "62c7bb3aa1cac9c2":
            b_sizes, a_sizes = metadata_sizes(before, b_frames), metadata_sizes(after, a_frames)
            if sum(a is not None for a in a_sizes) != report["updated_metadata_rows"]:
                raise ValueError("Program metadata relocation count")
            if any(b is not None and a != b + 16 or b is None and a is not None
                   for b, a in zip(b_sizes, a_sizes)):
                raise ValueError("Program material size relocation")
        verified.append({"material": name, "programs": len(b_frames),
                         "changed_pixel_programs": len(changed), "registered_groups": registration,
                         "candidate_sha256": digest(after)})
    if len(verified) != 3:
        raise ValueError("Incomplete liquid-fire material verification")
    print(json.dumps(verified, indent=2))


if __name__ == "__main__":
    main()
