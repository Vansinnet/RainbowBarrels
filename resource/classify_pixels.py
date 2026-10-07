"""Inventory the output paths of the distinct barrel pixel programs."""

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1] / "analysis"
SOURCES = ("shader-color-trace-24735202", "shader-remaining-24735202")
STORE = re.compile(r"call void @dx\.op\.storeOutput\.f32\(i32 5, i32 0, i32 0, i8 ([0-3]), float ([^)]+)\)")


def main():
    rows = []
    for source in SOURCES:
        folder = ROOT / source
        for item in json.loads((folder / "provenance.json").read_text())["programs"]:
            file = folder / (item["program"] + ".ll.txt")
            text = file.read_text()
            stores = STORE.findall(text)
            per_channel = [[v for channel, v in stores if channel == str(i)] for i in range(4)]
            if stores and any(not values for values in per_channel):
                raise ValueError(f"Partial target output in {file}")
            body = text.split("define void @ps_main() {", 1)[1].split("\n}\n", 1)[0]
            rows.append({"program": item["program"], "output_counts": [len(v) for v in per_channel],
                         "output_sources": [v[0] if len(v) == 1 else None for v in per_channel],
                         "branches": body.count(" br i1 "),
                         "texture_samples": len(re.findall(r"@dx\.op\.sample(?:Level|Grad|Bias)?\.f32\(", body))})
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
