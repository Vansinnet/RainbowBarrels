"""Inspect exact resource-metadata rows before material-buffer relocation."""

import hashlib
import json
from pathlib import Path
import struct

from profile_exports import Cursor
from profile_shaders import inventory, old


ROOT = Path(__file__).resolve().parents[1] / "analysis"
TARGETS = ("be9333164c3ddf4a", "debe1ef92005d87e", "e14900c258cc9b8e")


def main():
    manifests = (
        (ROOT / "stock-materials-24735202/provenance.json", "materials", "identity", "material_file", "source_sha256"),
        (ROOT / "stock-parents-24735202/provenance.json", "parents", "parent", "extracted_file", "sha256"),
    )
    result = []
    namehash = old.murmur64(b"c_material_exports") >> 32
    for manifest, section, identity, filename, digest in manifests:
        records = json.loads(manifest.read_text())[section]
        for item in records:
            if item[identity] not in TARGETS:
                continue
            data = (manifest.parent / item[filename]).read_bytes()
            if hashlib.sha256(data).hexdigest() != item[digest]:
                raise ValueError("Stock material identity")
            _, _, _, so, ss, _, _ = struct.unpack_from("<7I", data)
            shader = data[so:so + ss]
            fields = struct.unpack_from("<12I", shader)
            frames = inventory(data)
            profiles = []
            for i in sorted(set((0, 1, 2, len(frames) // 2, len(frames) - 1))):
                frame = frames[i]["offset"]
                size, = struct.unpack_from("<I", shader, frame - 4)
                c = Cursor(shader)
                c.pos = frame + size
                header = c.words(4)
                rows = c.table(6)
                profiles.append({"index": i, "stage": frames[i]["stage"],
                                 "metadata_header": header,
                                 "material_rows": [row for row in rows if row[0] == namehash],
                                 "other_buffer_sizes": [(f"{row[0]:08x}", row[2]) for row in rows]})
            result.append({"material": item[identity], "name_hash": f"{namehash:08x}",
                           "groups": struct.unpack_from("<I", shader, fields[8])[0], "profiles": profiles})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
