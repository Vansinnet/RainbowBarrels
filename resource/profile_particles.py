"""Profile the exact extracted particle cloud headers; no game writes."""

import hashlib
import json
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parents[1] / "analysis" / "stock-particles-24735202"


def profile(data):
    if len(data) < 82 or struct.unpack_from("<I", data, 38)[0] != 102:
        raise ValueError("Unknown particle layout")
    body = data[38:]
    variables, count = struct.unpack_from("<II", body, 36)
    if variables > 64 or count > 64:
        raise ValueError("Particle cloud count")
    offset = 44 + variables * 16
    rows = []
    for index in range(count):
        if offset + 576 > len(body):
            raise ValueError("Cloud header bounds")
        words = struct.unpack_from("<144I", body, offset)
        slots, stride = words[3:5]
        if slots > 16 or sum(words[5:5 + slots]) != stride:
            raise ValueError("Cloud slot layout")
        sections = [words[i] for i in (134, 136, 137, 140, 143)]
        if not (576 <= sections[0] <= sections[1] <= sections[2] <= sections[3]
                <= sections[4] <= len(body) - offset):
            raise ValueError("Cloud sections")
        visualizer = offset + sections[3]
        candidate = (f"{struct.unpack_from('<Q', body, visualizer + 12)[0]:016x}"
                     if slots and visualizer + 20 <= offset + sections[4] else None)
        rows.append({"index": index, "cloud_id32": f"{words[0]:08x}",
                     "visualizer_type": (struct.unpack_from("<I", body, visualizer)[0]
                                         if visualizer + 4 <= offset + sections[4] else None),
                     "slots": slots, "material_candidate": candidate,
                     "body_offset": offset, "record_size": sections[4],
                     "visualizer_offset": visualizer, "visualizer_size": sections[4] - sections[3]})
        offset += sections[4]
    if offset != len(body):
        raise ValueError("Unconsumed particle body")
    return {"version": 102, "variables": variables, "clouds": rows}


if __name__ == "__main__":
    manifest = json.loads((HERE / "provenance.json").read_text())
    report = []
    for row in manifest["particles"]:
        data = (HERE / row["extracted_file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != row["extracted_sha256"]:
            raise ValueError("Extracted resource drift")
        report.append({"effect": row["effect"], "source": row["game_source"],
                       "particle_sha256": row["extracted_sha256"], **profile(data)})
    print(json.dumps(report, indent=2))
