"""Identify color-writing versus feedback liquid-fire programs."""

import json
from pathlib import Path

from classify_pixels import STORE


ROOT = Path(__file__).resolve().parents[1] / "analysis/liquid-shaders-24735202"


def main():
    result = []
    for row in json.loads((ROOT / "provenance.json").read_text())["programs"]:
        text = (ROOT / (row["program"] + ".ll.txt")).read_text()
        stores = STORE.findall(text)
        per_channel = [sum(channel == str(i) for channel, _ in stores) for i in range(4)]
        if stores and per_channel != [1, 1, 1, 1]:
            raise ValueError("Unclassified partial color output")
        result.append({"material": row["material"], "program": row["program"],
                       "color_target_writes": per_channel})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
