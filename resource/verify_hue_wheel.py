"""Independent readback of all 720 offline barrel particle variants."""

import hashlib
import json
from pathlib import Path
import struct

from analyze_effects import GAME, SOURCES, decode_bundle_parts, decoder
from author_light_graphs import rgb
from build_green_bundle import MATERIAL, PARTICLES, ROOT, sha
from inspect_stock import murmur64
from locate_light_colors import candidates as light_colors
from profile_particles import HERE, profile


OUT = ROOT / "analysis/hue-wheel-bundle-24735202"
LUA_CLOUD_PREFIXES = {"explosive": "RainbowBarrels_explosive_", "fire": "RainbowBarrels_fire_"}


def main():
    report = json.loads((OUT / "report.json").read_text())
    package = (OUT / "bundle/98bb14b1d247a0c8").read_bytes()
    if sha(package) != report["candidate_bundle_sha256"]:
        raise ValueError("Candidate physical SHA-256 changed")
    source = (GAME / SOURCES[1][0]).read_bytes()
    if sha(source) != report["stock_bundle_sha256"]:
        raise ValueError("Stock physical SHA-256 changed")
    stock, _ = decode_bundle_parts(source, decoder())
    after, padding = decode_bundle_parts(package, lambda block: block)
    if len(stock) != 423 or len(after) != 1156 or after[:len(stock)] != stock or any(padding):
        raise ValueError("Original records, index, or output padding")
    material_rows = {item["path"]: item for item in report["added_material_streams"]}
    if len(material_rows) != 13:
        raise ValueError("Generated material set")
    materials = set()
    for identity, raw, descriptors in after[423:436]:
        if identity[0] != MATERIAL or identity[2] != 4 or descriptors != [(0, 1, len(raw) - 38, 1, 0)]:
            raise ValueError("Generated material registration profile")
        filename = f"bundle/data/rb/{identity[1]:016x}"
        expected = material_rows.get(filename)
        data = (OUT / filename).read_bytes()
        if (not expected or sha(data) != expected["sha256"]
                or raw[38:] != f"data/rb/{identity[1]:016x}".encode("ascii") + bytes(4)):
            raise ValueError("Material stream pointer or payload identity")
        materials.add(identity[1])
    stock_effects = {label: next(raw for identity, raw, _ in stock if identity[:2] ==
                                 (PARTICLES, murmur64(effect))) for label, effect in (
                                     ("explosive", "content/fx/particles/explosions/frag_grenade_01"),
                                     ("fire", "content/fx/particles/destructibles/explosive_barrel_explosion"))}
    expected_particles = {(p["effect"], p["hue"]): p for p in report["generated_particles"]}
    if len(expected_particles) != 720:
        raise ValueError("Hue particle report set")
    checked = {"explosive": set(), "fire": set()}
    for identity, raw, descriptors in after[436:]:
        if identity[0] != PARTICLES or identity[2] != 0 or len(descriptors) != 1:
            raise ValueError("Generated particle registration profile")
        possible = [p for p in report["generated_particles"] if murmur64(p["path"]) == identity[1]]
        if len(possible) != 1:
            raise ValueError("Generated particle identity")
        row = possible[0]
        label, hue = row["effect"], row["hue"]
        if not 0 <= hue < 360 or sha(raw) != row["sha256"] or hue in checked[label]:
            raise ValueError("Per-hue candidate identity or duplication")
        checked[label].add(hue)
        stock_profile = profile(stock_effects[label])["clouds"]
        current = profile(raw)["clouds"]
        if len(current) != len(stock_profile):
            raise ValueError("Changed particle cloud count")
        light_count = 0
        for old, new in zip(stock_profile, current):
            if old["visualizer_type"] != new["visualizer_type"] or old["record_size"] != new["record_size"]:
                raise ValueError("Unrelated cloud layout")
            if old["visualizer_type"] == 0 and old["material_candidate"]:
                expected_cloud = LUA_CLOUD_PREFIXES[label] + f"{old['index']:02d}"
                if (int(new["material_candidate"], 16) not in materials
                        or new["cloud_id32"] != f"{murmur64(expected_cloud) >> 32:08x}"):
                    raise ValueError("Billboard material or cloud lookup")
            if old["visualizer_type"] == 1:
                before = stock_effects[label][38 + old["visualizer_offset"]:][:old["visualizer_size"]]
                current_bytes = raw[38 + new["visualizer_offset"]:][:new["visualizer_size"]]
                before_graph = light_colors(before)
                current_graph = light_colors(current_bytes)
                if len(before_graph) != 1 or len(current_graph) != 1:
                    raise ValueError("Light ColorGraph readback")
                if any(before_graph[0][field] != current_graph[0][field]
                       for field in ("offset", "mode", "keys", "times")):
                    raise ValueError("Light ColorGraph layout or timing")
                for old_rgb, new_rgb in zip(before_graph[0]["active_rgb"], current_graph[0]["active_rgb"]):
                    expected_rgb = [max(old_rgb) * channel for channel in rgb(hue)]
                    if any(abs(a - b) > max(0.0001, max(old_rgb) * 0.00001)
                           for a, b in zip(expected_rgb, new_rgb)):
                        raise ValueError("Light selected hue/amplitude")
                light_count += 1
        if light_count != 2:
            raise ValueError("Both light curves must be present")
    if any(hues != set(range(360)) for hues in checked.values()):
        raise ValueError("Incomplete color wheel")
    print(json.dumps({"bundle_sha256": sha(package), "preserved_stock_resources": len(stock),
                      "custom_materials": len(materials), "checked_particles": sum(map(len, checked.values())),
                      "hues_per_barrel": {key: len(value) for key, value in checked.items()},
                      "status": "offline readback; native loading and runtime color untested"}, indent=2))


if __name__ == "__main__":
    main()
