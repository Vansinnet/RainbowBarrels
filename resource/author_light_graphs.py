"""Author exact-profile color-graph candidates for barrel particle lights."""

import hashlib
import json
from pathlib import Path
import struct

from locate_light_colors import candidates
from profile_particles import HERE, profile


OUT = Path(__file__).resolve().parents[1] / "analysis" / "light-green-trial-24735202"
TARGETS = {
    "frag_grenade_01": ((4, 3, 5), (5, 3, 3)),
    "explosive_barrel_explosion": ((3, 2, 4), (4, 9, 4)),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rgb(hue):
    phase = hue / 60
    chroma = 1.0
    x = chroma * (1 - abs(phase % 2 - 1))
    colors = ((chroma, x, 0), (x, chroma, 0), (0, chroma, x),
              (0, x, chroma), (x, 0, chroma), (chroma, 0, x))
    return colors[int(phase) % 6]


def author(source, hue, expectations):
    particle = profile(source)
    result = bytearray(source)
    before = {}
    changed = []
    for index, expected_mode, expected_keys in expectations:
        row = particle["clouds"][index]
        if row["visualizer_type"] != 1 or row["visualizer_size"] != 692:
            raise ValueError("Unexpected light visualizer profile")
        start = 38 + row["visualizer_offset"]
        data = source[start:start + row["visualizer_size"]]
        matches = candidates(data)
        if len(matches) != 1 or (matches[0]["offset"], matches[0]["mode"], matches[0]["keys"]) != (352, expected_mode, expected_keys):
            raise ValueError("ColorGraph position, type, or key count")
        span = start + 352 + 44
        for key in range(expected_keys):
            offset = span + key * 12
            old = struct.unpack_from("<3f", source, offset)
            if not all(0 <= channel <= 10050 for channel in old):
                raise ValueError("Light RGB bounds")
            value = max(old)
            target = tuple(value * channel for channel in rgb(hue))
            before[offset] = source[offset:offset + 12]
            struct.pack_into("<3f", result, offset, *target)
            changed.append({"cloud": index, "key": key, "offset": offset,
                            "source_rgb": old, "target_rgb": target})
    reverse = bytearray(result)
    for offset, previous in before.items():
        reverse[offset:offset + 12] = previous
    if reverse != source or len(result) != len(source):
        raise ValueError("ColorGraph-only reverse roundtrip")
    for index, expected_mode, expected_keys in expectations:
        row = particle["clouds"][index]
        start = 38 + row["visualizer_offset"]
        found = candidates(result[start:start + 692])
        if len(found) != 1 or (found[0]["offset"], found[0]["mode"], found[0]["keys"]) != (352, expected_mode, expected_keys):
            raise ValueError("ColorGraph readback")
    return bytes(result), changed


def main():
    if OUT.exists():
        raise ValueError("Research directory already exists")
    inputs = json.loads((HERE / "provenance.json").read_text())["particles"]
    reports, payloads = [], {}
    for item in inputs:
        path = item["extracted_file"]
        if "98bb14b1d247a0c8-frag" in path:
            continue
        name = Path(path).stem.split("-", 1)[1]
        source = (HERE / path).read_bytes()
        if sha(source) != item["extracted_sha256"]:
            raise ValueError("Stock particle identity changed")
        candidate, changes = author(source, 120, TARGETS[name])
        output = name + "-green.particles"
        payloads[output] = candidate
        reports.append({"effect": item["effect"], "source_sha256": sha(source),
                        "candidate_sha256": sha(candidate), "candidate_bytes": len(candidate),
                        "changed_light_keys": changes, "file": output})
    if len(reports) != 2:
        raise ValueError("Two explosion particles required")
    OUT.mkdir(parents=True)
    for name, data in payloads.items():
        (OUT / name).write_bytes(data)
    (OUT / "report.json").write_text(json.dumps({"build": "24735202", "hue": 120,
                                                 "status": "offline light-graph candidates; no game result",
                                                 "particles": reports}, indent=2) + "\n")
    print(json.dumps([{"effect": row["effect"], "changed_light_keys": len(row["changed_light_keys"]),
                      "candidate_sha256": row["candidate_sha256"]} for row in reports], indent=2))


if __name__ == "__main__":
    main()
