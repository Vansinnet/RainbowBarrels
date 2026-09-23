"""Map only the stock persistent prop-fire particle/material graph."""

import hashlib
import json
from pathlib import Path

from locate_light_colors import candidates
from profile_particles import profile


ROOT = Path(__file__).resolve().parents[1] / "analysis/liquid-stock-24735202"


def main():
    evidence = json.loads((ROOT / "provenance.json").read_text())["particles"]
    profiles = []
    for item in evidence:
        if "b224998193576995" not in item["bundle"]:
            continue
        data = (ROOT / item["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["record_sha256"]:
            raise ValueError("Original liquid particle identity")
        records = profile(data)["clouds"]
        for row in records:
            if row["visualizer_type"] == 1:
                start, size = row["visualizer_offset"], row["visualizer_size"]
                row["light_graph_candidates"] = candidates(data[38 + start:38 + start + size])
        profiles.append({"effect": item["effect"], "size": len(data), "clouds": records})
    print(json.dumps(profiles, indent=2))


if __name__ == "__main__":
    main()
