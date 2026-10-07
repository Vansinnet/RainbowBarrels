"""Author only the retained type-2 ground-cloud RGB curve for 360 filled hues."""

import json
from pathlib import Path
import struct

from analyze_effects import decode_bundle_parts
from author_light_graphs import rgb
from build_green_bundle import bundle, sha
from inspect_stock import murmur64
from locate_light_colors import candidates
from profile_particles import profile


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "analysis/liquid-hue-wheel-24735202"
OUT = ROOT / "analysis/liquid-floor-graph-trial-24735202"
PACKAGE = "b224998193576995"
BASE_SHA = "ba72ce819fa19d2c7c9ba3449e58013c2a3b1247f109d082da32682a2b0aae31"
EXPECTED_RGB = ((0.0, 0.0, 0.0), (255.0, 255.0, 255.0),
                (229.0, 229.0, 229.0), (0.0, 0.0, 0.0))


def recolor(source, hue):
    clouds = profile(source)["clouds"]
    if len(clouds) != 4 or clouds[2]["visualizer_type"] != 2 or clouds[2]["visualizer_size"] != 728:
        raise ValueError("Exact persistent-fire type-2 visualizer")
    start = 38 + clouds[2]["visualizer_offset"]
    visualizer = source[start:start + 728]
    matches = candidates(visualizer)
    if (len(matches) != 1 or matches[0]["offset"] != 480
            or matches[0]["mode"] != 3 or matches[0]["keys"] != 4
            or tuple(tuple(row) for row in matches[0]["active_rgb"]) != EXPECTED_RGB):
        raise ValueError("Stock white/gray type-2 ColorGraph")
    result = bytearray(source)
    offsets = []
    for key in (1, 2):
        offset = start + 480 + 44 + key * 12
        intensity = EXPECTED_RGB[key][0]
        target = tuple(intensity * channel for channel in rgb(hue))
        if struct.unpack_from("<3f", source, offset) != EXPECTED_RGB[key]:
            raise ValueError("Exact type-2 RGB key offset")
        struct.pack_into("<3f", result, offset, *target)
        offsets.append(offset)
    restored = bytearray(result)
    for offset in offsets:
        restored[offset:offset + 12] = source[offset:offset + 12]
    if restored != source or len(result) != len(source):
        raise ValueError("Only two active type-2 RGB keys may change")
    after = candidates(bytes(result)[start:start + 728])
    if len(after) != 1 or after[0]["offset"] != 480 or after[0]["keys"] != 4:
        raise ValueError("Authored type-2 curve structure")
    return bytes(result), offsets


def main():
    if OUT.exists():
        raise ValueError("Output already exists")
    original = (BASE / "bundle" / PACKAGE).read_bytes()
    report = json.loads((BASE / "report.json").read_text())
    if sha(original) != BASE_SHA or report["candidate_bundle_sha256"] != BASE_SHA:
        raise ValueError("Previously installed hue-wheel bundle changed")
    entries, padding = decode_bundle_parts(original, lambda block: block)
    if len(entries) != 1910 or any(padding):
        raise ValueError("Existing wheel record count and padding")
    index = [identity for identity, _, _ in entries]
    resources = [raw for _, raw, _ in entries]
    positions = {identity[:2]: number for number, identity in enumerate(index)}
    changes = []
    for hue in range(360):
        path = f"content/fx/particles/rainbow_barrels/fire_lingering_filled_hue_{hue:03d}"
        position = positions.get((murmur64("particles"), murmur64(path)))
        if position is None or position < 110:
            raise ValueError("Missing indexed filled particle")
        before = resources[position]
        after, offsets = recolor(before, hue)
        resources[position] = after
        changes.append({"effect": path, "hue": hue, "index": position,
                        "original_sha256": sha(before), "candidate_sha256": sha(after),
                        "rgb_key_offsets": offsets})
    if len(changes) != 360 or any(resources[n] != entries[n][1] for n in range(110)):
        raise ValueError("Stock and previous custom resources must be preserved")
    candidate = bundle(index, resources, original[12:268])
    readback, remainder = decode_bundle_parts(candidate, lambda block: block)
    if ([key for key, _, _ in readback] != index or [raw for _, raw, _ in readback] != resources
            or any(remainder)):
        raise ValueError("Ground curve bundle complete readback")
    OUT.mkdir(parents=True)
    (OUT / "bundle").mkdir()
    (OUT / "bundle" / PACKAGE).write_bytes(candidate)
    summary = {"build": "24735202", "base_bundle_sha256": BASE_SHA,
               "candidate_bundle_sha256": sha(candidate), "resource_count": 1910,
               "filled_particles_recolored": 360, "rim_particles_unchanged": 360,
               "material_streams_unchanged": 1080, "changes": changes,
               "status": "offline exact type-2 curve candidate; effect on floor highlights untested"}
    (OUT / "report.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: summary[key] for key in ("base_bundle_sha256", "candidate_bundle_sha256",
                                                 "resource_count", "filled_particles_recolored",
                                                 "status")}, indent=2))


if __name__ == "__main__":
    main()
