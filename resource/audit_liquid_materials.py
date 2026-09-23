"""Check stock liquid-fire shader/profile identity and feasible material exports."""

import hashlib
import json
from pathlib import Path
import struct

from probe_defaults import defaults
from profile_exports import groups, template
from profile_shaders import inventory


ROOT = Path(__file__).resolve().parents[1] / "analysis/liquid-stock-24735202"


def main():
    rows = json.loads((ROOT / "materials-provenance.json").read_text())["materials"]
    report = []
    for item in rows:
        data = (ROOT / "materials" / item["retained_file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["stream_sha256"]:
            raise ValueError("Stock material identity")
        _, mo, ms, so, ss, _, _ = struct.unpack_from("<7I", data)
        parsed = template(data[mo:mo + ms])
        info = {"material": item["identity"], "parent_materials": item["parents"],
                "shader_bytes": ss, "template_exports": len(parsed["reflection"]),
                "material_values_bytes": parsed["values_size"]}
        if ss:
            shader = data[so:so + ss]
            fields = struct.unpack_from("<12I", shader)
            start, size = fields[8:10]
            registered = groups(shader[start:start + size])
            values = defaults(shader[fields[5]:])
            frames = inventory(data)
            info.update(registration_groups=len(registered), material_allocations=sorted({g["allocation"] for g in registered}),
                        default_count=len(values), programs=len(frames),
                        stage_counts={str(stage): sum(row["stage"] == stage for row in frames)
                                      for stage in sorted({row["stage"] for row in frames})},
                        unique_pixel_programs=len({row["dxbc_sha256"] for row in frames if row["stage"] == 0}))
        report.append(info)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
