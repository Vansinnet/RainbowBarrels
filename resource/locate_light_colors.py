"""Find bounded ColorGraph-shaped spans in stock light visualizers."""

import hashlib
import json
import math
from pathlib import Path
import struct

from profile_particles import HERE, profile


def candidates(data):
    result = []
    for offset in range(0, len(data) - 168 + 1, 4):
        mode, = struct.unpack_from("<I", data, offset)
        if not 0 <= mode <= 12:
            continue
        times = struct.unpack_from("<10f", data, offset + 4)
        values = struct.unpack_from("<30f", data, offset + 44)
        trailer, = struct.unpack_from("<I", data, offset + 164)
        if (not 2 <= trailer <= 10 or any(not math.isfinite(value) for value in times + values)
                or times[0] != 0 or times[trailer - 1] > 1
                or any(a >= b for a, b in zip(times[:trailer - 1], times[1:trailer]))
                or not all(time >= 10000 for time in times[trailer:])
                or not all(0 <= value <= 10050 for value in values)
                ):
            continue
        result.append({"offset": offset, "mode": mode, "keys": trailer,
                       "times": times[:trailer],
                       "active_rgb": [values[3 * i:3 * i + 3] for i in range(trailer)]})
    return result


def main():
    manifest = json.loads((HERE / "provenance.json").read_text())
    results = []
    for item in manifest["particles"]:
        if item["game_source"].endswith("98bb14b1d247a0c8") and item["effect"].endswith("frag_grenade_01"):
            continue
        data = (HERE / item["extracted_file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["extracted_sha256"]:
            raise ValueError("Stock particle identity")
        for row in profile(data)["clouds"]:
            if row["visualizer_type"] != 1:
                continue
            start, length = row["visualizer_offset"], row["visualizer_size"]
            visualizer = data[38 + start:38 + start + length]
            results.append({"effect": item["effect"], "cloud": row["index"],
                            "visualizer_sha256": hashlib.sha256(visualizer).hexdigest(),
                            "candidate_graphs": candidates(visualizer)})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
