"""Estimate the exact package growth from independent per-degree light variants."""

import json
from pathlib import Path
import struct

from analyze_effects import GAME, SOURCES
from profile_particles import HERE


def main():
    source = GAME / SOURCES[1][0]
    with source.open("rb") as file:
        header = file.read(12)
        count, = struct.unpack_from("<I", header, 8)
        file.seek(268 + count * 20)
        chunks, = struct.unpack("<I", file.read(4))
        file.seek(4 * chunks, 1)
        file.seek((-file.tell()) % 16, 1)
        logical, reserved = struct.unpack("<II", file.read(8))
    if reserved or chunks != (logical + 0x7FFFF) // 0x80000:
        raise ValueError("Stock bundle length/chunk identity")
    profile = json.loads((HERE / "provenance.json").read_text())["particles"]
    targets = [row for row in profile if row["game_source"] == str(source)]
    if len(targets) != 2:
        raise ValueError("Expected both target particles in global bundle")
    for hues in (360, 120, 72):
        increase = sum(row["extracted_size"] for row in targets) * hues
        newlogical = logical + increase + (hues * 2 + 13) * 68
        print(json.dumps({"hue_variants": hues, "stock_resources": count, "stock_chunks": chunks,
                          "stock_logical_bytes": logical, "minimum_generated_logical_bytes": newlogical,
                          "minimum_generated_chunks": (newlogical + 0x7FFFF) // 0x80000,
                          "minimum_index_resources": count + hues * 2 + 13}, indent=2))


if __name__ == "__main__":
    main()
