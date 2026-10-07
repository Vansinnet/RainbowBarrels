"""Independent offline inventory of new persistent-fire particles and streams."""

import hashlib
import json
from pathlib import Path

from analyze_effects import GAME, decode_bundle_parts, decoder
from inspect_stock import murmur64
from profile_particles import profile


ROOT = Path(__file__).resolve().parents[1] / "analysis/liquid-bundle-trial-24735202"
PACKAGE = "b224998193576995"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    report = json.loads((ROOT / "report.json").read_text())
    source = (GAME / "bundle" / PACKAGE).read_bytes()
    target = (ROOT / "bundle" / PACKAGE).read_bytes()
    if sha(source) != report["source_bundle_sha256"] or sha(target) != report["candidate_bundle_sha256"]:
        raise ValueError("Physical bundle/source SHA-256")
    stock, _ = decode_bundle_parts(source, decoder())
    records, padding = decode_bundle_parts(target, lambda block: block)
    if len(stock) != 103 or len(records) != 110 or records[:103] != stock or any(padding):
        raise ValueError("Unchanged original resources in liquid package")
    assets = {item["identity"]: item for item in report["added_assets"]}
    custom_materials = {murmur64(name) for name, item in assets.items() if item["kind"] == "material"}
    if len(custom_materials) != 5:
        raise ValueError("Missing generated material identities")
    checked = 0
    for identity, record, descriptors in records[103:]:
        name = next((key for key in assets if murmur64(key) == identity[1]), None)
        item = assets.get(name)
        if not item or sha(record) != item["sha256"] and item["kind"] == "particle":
            raise ValueError("Generated logical-resource identity")
        if item["kind"] == "material":
            if identity[0] != murmur64("material") or identity[2] != 4:
                raise ValueError("New material index mode")
            pointer = f"data/rb/{identity[1]:016x}".encode("ascii") + bytes(4)
            if record[38:] != pointer:
                raise ValueError("Generated material pointer")
            stream = (ROOT / item["stream"]).read_bytes()
            if sha(stream) != item["sha256"] or len(stream) != item["bytes"]:
                raise ValueError("Generated shader-bearing material payload")
        else:
            if identity[0] != murmur64("particles") or identity[2] != 0 or sha(record) != item["sha256"]:
                raise ValueError("New particle index mode or raw bytes")
            clouds = profile(record)["clouds"]
            expected = {row["cloud"]: row for row in item["clouds"]}
            for row in clouds:
                if row["index"] not in expected:
                    continue
                cloud = expected[row["index"]]
                if (row["cloud_id32"] != f"{murmur64(cloud['name']) >> 32:08x}"
                        or int(row["material_candidate"], 16) not in custom_materials):
                    raise ValueError("Liquid billboard material/cloud binding")
            checked += 1
    if checked != 2:
        raise ValueError("Both persistent-fire particle variants required")
    print(json.dumps({"bundle_sha256": sha(target), "unchanged_stock_resources": len(stock),
                      "custom_materials": len(custom_materials), "custom_particles": checked,
                      "status": "offline readback; client template ownership and in-game color untested"}, indent=2))


if __name__ == "__main__":
    main()
