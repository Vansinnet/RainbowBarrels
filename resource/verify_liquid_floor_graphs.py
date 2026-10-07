"""Independent byte-level verification of all 360 authored type-2 RGB curves."""

import colorsys
import hashlib
import json
from pathlib import Path
import struct

from analyze_effects import decode_bundle_parts
from inspect_stock import murmur64
from locate_light_colors import candidates
from profile_particles import profile


ROOT = Path(__file__).resolve().parents[1] / "analysis"
BASE = ROOT / "liquid-hue-wheel-24735202"
TRIAL = ROOT / "liquid-floor-graph-trial-24735202"
PACKAGE = "b224998193576995"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    report = json.loads((TRIAL / "report.json").read_text())
    before_bundle = (BASE / "bundle" / PACKAGE).read_bytes()
    after_bundle = (TRIAL / "bundle" / PACKAGE).read_bytes()
    if sha(before_bundle) != report["base_bundle_sha256"] or sha(after_bundle) != report["candidate_bundle_sha256"]:
        raise ValueError("Pinned physical bundle identities")
    before, _ = decode_bundle_parts(before_bundle, lambda block: block)
    after, padding = decode_bundle_parts(after_bundle, lambda block: block)
    if (len(before) != 1910 or len(after) != 1910 or any(padding)
            or [identity for identity, _, _ in before] != [identity for identity, _, _ in after]):
        raise ValueError("Source/target resource inventories")
    changed = {row["index"]: row for row in report["changes"]}
    if len(changed) != 360 or len(report["changes"]) != 360:
        raise ValueError("Exactly 360 indexed changes required")
    for index, (old, new) in enumerate(zip(before, after)):
        identity, original, descriptors = old
        current = new[1]
        row = changed.get(index)
        if row is None:
            if old != new:
                raise ValueError("Unrelated liquid resource changed")
            continue
        hue = row["hue"]
        name = f"content/fx/particles/rainbow_barrels/fire_lingering_filled_hue_{hue:03d}"
        if (row["effect"] != name or identity[:2] != (murmur64("particles"), murmur64(name))
                or sha(original) != row["original_sha256"] or sha(current) != row["candidate_sha256"]
                or len(original) != len(current) or descriptors != new[2]):
            raise ValueError("Changed particle identity or preservation")
        clouds = profile(original)["clouds"]
        if len(clouds) != 4 or clouds[2]["visualizer_type"] != 2 or clouds[2]["visualizer_size"] != 728:
            raise ValueError("Ground non-billboard profile")
        start = 38 + clouds[2]["visualizer_offset"]
        old_graph = candidates(original[start:start + 728])
        new_graph = candidates(current[start:start + 728])
        if (len(old_graph) != 1 or len(new_graph) != 1 or old_graph[0]["offset"] != 480
                or new_graph[0]["offset"] != 480 or new_graph[0]["mode"] != 3
                or old_graph[0]["times"] != new_graph[0]["times"]
                or old_graph[0]["active_rgb"] != [(0.0, 0.0, 0.0), (255.0,) * 3,
                                                    (229.0,) * 3, (0.0, 0.0, 0.0)]):
            raise ValueError("Original and authored four-key color graphs")
        r, g, b = colorsys.hsv_to_rgb(hue / 360, 1, 1)
        expected = [(0.0, 0.0, 0.0), (255 * r, 255 * g, 255 * b),
                    (229 * r, 229 * g, 229 * b), (0.0, 0.0, 0.0)]
        if any(abs(observed - wanted) > 1e-4 for old_rgb, desired in
               zip(new_graph[0]["active_rgb"], expected) for observed, wanted in zip(old_rgb, desired)):
            raise ValueError("Type-2 hue curve value")
        spans = [start + 480 + 44 + key * 12 for key in (1, 2)]
        if row["rgb_key_offsets"] != spans:
            raise ValueError("ColorGraph RGB offsets")
        restored = bytearray(current)
        for offset in spans:
            restored[offset:offset + 12] = original[offset:offset + 12]
        if bytes(restored) != original:
            raise ValueError("Unrelated particle byte delta")
    if len(changed) != report["filled_particles_recolored"]:
        raise ValueError("Bundle/report candidate count")
    print(json.dumps({"bundle_sha256": sha(after_bundle),
                      "unchanged_resource_records": len(before) - len(changed),
                      "recolored_type2_clouds": len(changed),
                      "status": "offline exact-curve readback; in-game floor behavior pending"}, indent=2))


if __name__ == "__main__":
    main()
