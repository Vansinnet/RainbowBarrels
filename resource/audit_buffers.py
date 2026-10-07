"""Find every witnessed material-exports buffer and its available scalar slots."""

import hashlib
import json
from pathlib import Path
import struct

from profile_exports import Cursor


ROOT = Path(__file__).resolve().parents[1] / "analysis"
KNOWN_EXPORT = 0x2CC3DCEE  # particle_max_size or shared particle size scalar witness


def main():
    results = []
    for directory, key, name, filename, digest in (
        ("stock-materials-24735202", "materials", "identity", "material_file", "source_sha256"),
        ("stock-parents-24735202", "parents", "parent", "extracted_file", "sha256"),
    ):
        root = ROOT / directory
        for item in json.loads((root / "provenance.json").read_text())[key]:
            data = (root / item[filename]).read_bytes()
            if hashlib.sha256(data).hexdigest() != item[digest]:
                raise ValueError("Stock material drift")
            _, _, _, so, ss, _, _ = struct.unpack_from("<7I", data)
            if not ss:
                continue
            shader = data[so:so + ss]
            start, size = struct.unpack_from("<II", shader, 32)
            c = Cursor(shader[start:start + size])
            groups, = c.words()
            matches = []
            growth_profiles = []
            for i in range(groups):
                key_hash, allocation = c.words(2)
                c.table(4)
                buffers, = c.words()
                all_buffers = []
                for j in range(buffers):
                    rows = c.table(5)
                    capacity, offset = c.words(2)
                    all_buffers.append((j, capacity, offset))
                    if any(row[2] == KNOWN_EXPORT for row in rows):
                        matches.append({"group": i, "group_key": f"{key_hash:08x}",
                                        "buffer_index": j, "size": capacity, "offset": offset,
                                        "allocation": allocation, "used": max(row[3] + row[4] for row in rows),
                                        "descriptors": len(rows)})
                c.table(7)
                n, = c.words()
                c.take(17 * n + 8)
                if i in (0, 1, groups - 1):
                    growth_profiles.append({"group": i, "allocation": allocation,
                                            "buffers": all_buffers})
            if c.pos != len(c.data):
                raise ValueError("Shader groups parser drift")
            results.append({"material": item[name], "groups": groups,
                            "matching_material_buffers": matches,
                            "sampled_group_buffers": growth_profiles})
    print(json.dumps([row for row in results if row["material"] in (
        "be9333164c3ddf4a", "debe1ef92005d87e", "e14900c258cc9b8e")], indent=2))


if __name__ == "__main__":
    main()
