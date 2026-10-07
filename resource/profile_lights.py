"""Compare exact type-1 barrel particle visualizers without editing their bytes."""

import hashlib
import json
from pathlib import Path
import struct

from profile_particles import HERE, profile


def main():
    manifest = json.loads((HERE / "provenance.json").read_text())
    result = []
    for item in manifest["particles"]:
        if "d2b0b18252164f5b" not in item["game_source"] and "explosive_barrel_explosion" not in item["effect"]:
            continue
        data = (HERE / item["extracted_file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["extracted_sha256"]:
            raise ValueError("Particle source drift")
        body = data[38:]
        lights = []
        for row in profile(data)["clouds"]:
            if row["visualizer_type"] != 1:
                continue
            start, size = row["visualizer_offset"], row["visualizer_size"]
            visualizer = body[start:start + size]
            if len(visualizer) != 692:
                raise ValueError("Unexpected light visualizer size")
            lights.append({"record": row["index"], "cloud_id": row["cloud_id32"],
                           "visualizer_sha256": hashlib.sha256(visualizer).hexdigest(),
                           "initial_words": [f"{value:08x}" for value in struct.unpack_from("<16I", visualizer)],
                           "color_candidates": {str(begin): [
                               {"offset": pos, "hex": f"{struct.unpack_from('<I', visualizer, pos)[0]:08x}",
                                "float": struct.unpack_from("<f", visualizer, pos)[0]}
                               for pos in range(begin, finish, 4)]
                               for begin, finish in ((352, 448), (552, 636))},
                           "visualizer_bytes": visualizer})
        if len(lights) != 2:
            raise ValueError("Two light records expected")
        before, after = (r["visualizer_bytes"] for r in lights)
        result.append({"effect": item["effect"],
                       "light_records": [{k: v for k, v in light.items() if k != "visualizer_bytes"}
                                         for light in lights],
                       "differing_visualizer_byte_offsets": [i for i, (a, b) in enumerate(zip(before, after))
                                                             if a != b]})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
