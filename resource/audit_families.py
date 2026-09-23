"""Check which shader-registration profiles share the first proven roundtrip."""

import hashlib
import json
from pathlib import Path
import struct

from probe_defaults import defaults
from profile_exports import groups, template


ROOT = Path(__file__).resolve().parents[1] / "analysis"


def main():
    inputs = []
    for directory, section, name_key, digest_key, file_key in (
        ("stock-materials-24735202", "materials", "identity", "source_sha256", "material_file"),
        ("stock-parents-24735202", "parents", "parent", "sha256", "extracted_file"),
    ):
        path = ROOT / directory
        for item in json.loads((path / "provenance.json").read_text())[section]:
            inputs.append((item[name_key], path / item[file_key], item[digest_key]))
    results = []
    for name, path, expected in inputs:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Source evidence changed: {name}")
        _, mo, ms, so, ss, _, _ = struct.unpack_from("<7I", data)
        row = {"material": name, "shader_bytes": ss}
        try:
            values = template(data[mo:mo + ms])
            row["export_count"] = len(values["reflection"])
            row["template_values"] = values["values_size"]
        except ValueError as error:
            row["template_error"] = str(error)
        if ss:
            shader = data[so:so + ss]
            header = struct.unpack_from("<12I", shader)
            start, length = header[8:10]
            row["registration_groups"] = struct.unpack_from("<I", shader, start)[0]
            try:
                parsed = groups(shader[start:start + length])
                row["registration_roundtrip"] = True
                row["allocations"] = sorted({g["allocation"] for g in parsed})
            except ValueError as error:
                row["registration_error"] = str(error)
            try:
                row["default_count"] = len(defaults(shader[header[5]:]))
            except ValueError as error:
                row["default_error"] = str(error)
        results.append(row)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
