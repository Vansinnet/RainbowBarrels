"""Offline 360-degree barrel effect index with shared authored hue material streams."""

import json
from pathlib import Path

from analyze_effects import GAME, SOURCES, decode_bundle_parts, decoder
from build_green_bundle import (ROOT, HERE, PARTICLES, MATERIAL, bundle, material_sources,
                                particle, resource_record, sha)
from inspect_stock import murmur64


OUT = ROOT / "analysis/hue-wheel-bundle-24735202"


def main():
    if OUT.exists():
        raise ValueError("Research output already exists")
    source = GAME / SOURCES[1][0]
    stock = source.read_bytes()
    evidence = json.loads((HERE / "provenance.json").read_text())["particles"]
    expected = next(row["source_sha256"] for row in evidence if row["game_source"] == str(source))
    if sha(stock) != expected:
        raise ValueError("Stock game bundle source changed")
    originals, tail = decode_bundle_parts(stock, decoder())
    if len(originals) != 423 or any(tail):
        raise ValueError("Exact stock bundle and final padding")
    index = [identity for identity, _, _ in originals]
    records = [raw for _, raw, _ in originals]
    occupied = {entry[:2] for entry in index}
    material_streams = material_sources()
    additions = {}
    for stock_id, data in sorted(material_streams.items()):
        name = "content/fx/materials/rainbow_barrels/" + stock_id
        key = murmur64(name)
        identity = (MATERIAL, key, 4)
        if identity[:2] in occupied:
            raise ValueError("Custom material collision")
        occupied.add(identity[:2])
        index.append(identity)
        records.append(resource_record(MATERIAL, key, f"data/rb/{key:016x}".encode("ascii") + bytes(4), True))
        additions[f"bundle/data/rb/{key:016x}"] = data
    reports = []
    targets = (("frag_grenade_01", "explosive"), ("explosive_barrel_explosion", "fire"))
    for basename, label in targets:
        row = next(item for item in evidence if item["game_source"] == str(source) and item["effect"].endswith(basename))
        original = next(raw for identity, raw, _ in originals
                        if identity[:2] == (PARTICLES, murmur64(row["effect"])))
        if sha(original) != row["extracted_sha256"]:
            raise ValueError("Particle resource source changed")
        cloud_names = None
        for hue in range(360):
            name, rewritten, details = particle(row["effect"], original, label, material_streams, hue)
            identity = PARTICLES, murmur64(name), 0
            if identity[:2] in occupied:
                raise ValueError("Custom particle identity collision")
            occupied.add(identity[:2])
            index.append(identity)
            records.append(rewritten)
            if cloud_names is None:
                cloud_names = details["billboard_cloud_names"]
            elif details["billboard_cloud_names"] != cloud_names:
                raise ValueError("Hue-dependent cloud lookup names")
            reports.append({"effect": label, "hue": hue, "path": name, "sha256": sha(rewritten),
                            "light_keys": details["light_keys"]})
    if len(index) != 1156 or len(additions) != 13 or len(reports) != 720:
        raise ValueError("Incomplete generated hue wheel")
    candidate = bundle(index, records, stock[12:268])
    reread, final_padding = decode_bundle_parts(candidate, lambda block: block)
    if (len(reread) != len(index) or [row[0] for row in reread] != index
            or [row[1] for row in reread] != records or any(final_padding)):
        raise ValueError("Expanded package full logical readback")
    OUT.mkdir(parents=True)
    (OUT / "bundle").mkdir()
    (OUT / "bundle/98bb14b1d247a0c8").write_bytes(candidate)
    (OUT / "bundle/data").mkdir()
    (OUT / "bundle/data/rb").mkdir()
    for relative, contents in additions.items():
        (OUT / relative).write_bytes(contents)
    summary = {"build": "24735202", "stock_bundle_sha256": sha(stock),
               "candidate_bundle_sha256": sha(candidate), "candidate_bundle_bytes": len(candidate),
               "stock_resources": len(originals), "candidate_resources": len(reread),
               "hue_particle_variants": len(reports),
               "added_material_streams": [{"path": relative, "bytes": len(contents), "sha256": sha(contents)}
                                          for relative, contents in sorted(additions.items())],
               "generated_particles": reports,
               "status": "offline candidate; neither installed nor shown to render"}
    (OUT / "report.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: summary[key] for key in ("stock_bundle_sha256", "candidate_bundle_sha256",
                                                  "candidate_bundle_bytes", "stock_resources",
                                                  "candidate_resources", "hue_particle_variants", "status")}, indent=2))


if __name__ == "__main__":
    main()
