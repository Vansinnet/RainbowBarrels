"""Independently reparse the first authored hue material and all shader frames."""

import hashlib
import json
from pathlib import Path
import struct

from experiment_hue import EXPORT_NAME
from probe_defaults import defaults
from profile_exports import groups, template
from profile_shaders import inventory, old


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "analysis/stock-materials-24735202/9cda55b98bbfc8ff.material"
CANDIDATE = ROOT / "analysis/hue-material-trial-24735202/hue.material"
REPORT = ROOT / "analysis/hue-material-trial-24735202/report.json"
PIXEL = ROOT / "analysis/hue-trial-24735202/candidate.dxbc"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inspect(data):
    version, mo, ms, so, ss, tail, ts = struct.unpack_from("<7I", data)
    if version != 61 or mo != 28 or so != mo + ms or so + ss != len(data):
        raise ValueError("Material outer bounds")
    material = template(data[mo:so])
    shader = data[so:so + ss]
    header = struct.unpack_from("<12I", shader)
    group, size, device, dev_size = header[8:12]
    if header[0] != 43 or not 48 <= group < group + size <= device < device + dev_size <= header[5] <= len(shader):
        raise ValueError("Shader sections")
    reports = groups(shader[group:group + size])
    settings = defaults(shader[header[5]:])
    frames = inventory(data)
    return material, reports, settings, frames, shader, header


def main():
    original, candidate = ORIGINAL.read_bytes(), CANDIDATE.read_bytes()
    evidence = json.loads(REPORT.read_text())
    if sha(original) != evidence["source_sha256"] or sha(candidate) != evidence["candidate_sha256"]:
        raise ValueError("Source/candidate identity")
    old_mat, old_groups, old_defaults, old_frames, old_shader, old_header = inspect(original)
    new_mat, new_groups, new_defaults, new_frames, new_shader, new_header = inspect(candidate)
    if len(old_frames) != 6 or len(new_frames) != 6:
        raise ValueError("Shader count")
    control_hash = old.murmur64(EXPORT_NAME.encode()) >> 32
    if (len(new_mat["reflection"]) != len(old_mat["reflection"]) + 1
            or new_mat["reflection"][:-1] != old_mat["reflection"]
            or new_mat["reflection"][-1][2] != control_hash
            or new_mat["values_size"] != old_mat["values_size"] + 4):
        raise ValueError("Material control export")
    if (len(new_defaults) != len(old_defaults) + 1 or new_defaults[:-1] != old_defaults
            or new_defaults[-1] != (control_hash, struct.pack("<f", 0))):
        raise ValueError("Shader material defaults")
    if len(old_groups) != len(new_groups) or any(
        [old_group["key"], old_group["allocation"], old_group["resources"]]
        != [new_group["key"], new_group["allocation"], new_group["resources"]]
        or [buf["size"] for buf in old_group["buffers"]]
        != [buf["size"] for buf in new_group["buffers"]]
        or sum(buf["descriptors"] for buf in new_group["buffers"])
        != sum(buf["descriptors"] for buf in old_group["buffers"]) + 1
        for old_group, new_group in zip(old_groups, new_groups)):
        raise ValueError("Shader registration drift")
    color_hash = sha(PIXEL.read_bytes())
    changed = [i for i, (before, after) in enumerate(zip(old_frames, new_frames))
               if before["dxbc_sha256"] != after["dxbc_sha256"]]
    if changed != [1, 3, 5] or any(new_frames[i]["dxbc_sha256"] != color_hash for i in changed):
        raise ValueError("Unexpected shader program change")
    if (old_shader[:20] != new_shader[:20]
            or old_shader[24:36] != new_shader[24:36]
            or old_shader[48:old_header[8]] != new_shader[48:new_header[8]]
            or old_header[3] != new_header[3]
            or old_header[7] != new_header[7]):
        raise ValueError("Unrelated shader sections changed")
    print(json.dumps({"candidate_sha256": sha(candidate), "source_programs": len(old_frames),
                      "changed_pixel_programs": changed, "old_group_count": len(old_groups),
                      "new_material_export": f"{control_hash:08x}"}, indent=2))


if __name__ == "__main__":
    main()
