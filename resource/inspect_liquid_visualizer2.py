"""Compare the stock ground-fire non-billboard visualizer with known byte profiles."""

import hashlib
import json
from pathlib import Path
import struct

from profile_particles import profile
from locate_light_colors import candidates


ROOT = Path(__file__).resolve().parents[1] / "analysis"
LIQUID = ROOT / "liquid-stock-24735202"
BARRELS = ROOT / "stock-particles-24735202"


def read_entry(folder, manifest, suffix):
    row = next(item for item in json.loads((folder / "provenance.json").read_text())["particles"]
               if item["effect"].endswith(suffix) and
               (folder == BARRELS or "b224998193576995" in item["bundle"]))
    key = "extracted_file" if folder == BARRELS else "file"
    digest = "extracted_sha256" if folder == BARRELS else "record_sha256"
    data = (folder / row[key]).read_bytes()
    if hashlib.sha256(data).hexdigest() != row[digest]:
        raise ValueError("Retained stock particle identity")
    return data


def main():
    ground = read_entry(LIQUID, "provenance.json", "/fire_lingering")
    explosion = read_entry(BARRELS, "provenance.json", "/frag_grenade_01")
    entries = []
    for label, source in (("persistent_fill", ground), ("explosion", explosion)):
        for row in profile(source)["clouds"]:
            if row["visualizer_type"] != 2:
                continue
            begin = 38 + row["visualizer_offset"]
            body = source[begin:begin + row["visualizer_size"]]
            words = struct.unpack_from("<32I", body)
            entries.append({"effect": label, "cloud": row["index"],
                            "visualizer_bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                            "color_graph_candidates": candidates(body),
                            "head_u32": [f"{word:08x}" for word in words],
                            "head_f32": list(struct.unpack_from("<16f", body))})
    if len(entries) != 2 or entries[0]["visualizer_bytes"] != 728:
        raise ValueError("Unexpected non-billboard visualizer inventory: " +
                         str([(row["effect"], row["cloud"], row["visualizer_bytes"]) for row in entries]))
    print(json.dumps(entries, indent=2))


if __name__ == "__main__":
    main()
