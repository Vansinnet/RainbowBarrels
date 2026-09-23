"""Package authenticated custom records and materials, never extracted stock bundles."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import uuid

from analyze_effects import decode_bundle_parts
from build_green_bundle import bundle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "payload"
BUILD = "24735202"
VERSION = "0.1.0-rc.1"
OODLE_SHA = "8595a4795f1e0c7f548598f3e2aa528b6be5456c6d934c665182eaecb04156c0"
SOURCES = (
    ("explosion", "98bb14b1d247a0c8", ROOT / "analysis/hue-wheel-bundle-24735202",
     423, "9086f577b55278286bc5cd72de529300d61ba15d2612ad66a1cbe8b272d4da48", 8236031),
    ("ground", "b224998193576995", ROOT / "analysis/liquid-floor-graph-trial-24735202",
     103, "775762aae54cfd5313856f8b097e2527774600e92df896d375e4af6b8916376d", 511383),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def put(root, relative, data):
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    if digest(destination.read_bytes()) != digest(data):
        raise ValueError("Payload readback failed: " + relative)


def main():
    if OUTPUT.exists():
        raise ValueError("Payload already exists; review its manifest before rebuilding")
    tmp = ROOT / (".payload-build-" + uuid.uuid4().hex)
    tmp.mkdir()
    try:
        manifest = {"format": 1, "product": "RainbowBarrels", "version": VERSION,
                    "steamAppId": "1361210", "steamBuild": BUILD,
                    "exeVersion": "1.3.770.210", "oodleSha256": OODLE_SHA,
                    "bundles": [], "streams": [], "modFiles": []}
        for label, name, folder, stock_count, stock_sha, stock_size in SOURCES:
            path = folder / "bundle" / name
            raw = path.read_bytes()
            report = json.loads((folder / "report.json").read_text())
            if digest(raw) != report["candidate_bundle_sha256"]:
                raise ValueError("Pinned authored bundle drift: " + label)
            entries, padding = decode_bundle_parts(raw, lambda block: block)
            if len(entries) <= stock_count or any(padding):
                raise ValueError("Stock/custom bundle resource boundaries: " + label)
            stock = entries[:stock_count]
            appended = entries[stock_count:]
            if len({entry[0][:2] for entry in entries}) != len(entries):
                raise ValueError("Duplicate bundle resource identity")
            stock_logical = b"".join(entry[1] for entry in stock)
            stock_index = raw[268:268 + stock_count * 20]
            extra_index = b"".join(struct.pack("<QQI", *entry[0]) for entry in appended)
            extra_records = b"".join(entry[1] for entry in appended)
            insert = extra_index + extra_records
            before = [entry[0] for entry in stock]
            after = [entry[0] for entry in appended]
            if bundle(before + after, [entry[1] for entry in entries], raw[12:268]) != raw:
                raise ValueError("Authenticated output cannot be rebuilt from stock plus additions")
            relative = f"inserts/{label}.bin"
            put(tmp, relative, insert)
            manifest["bundles"].append({"id": label, "target": "bundle/" + name,
                "stockSize": stock_size, "stockSha256": stock_sha, "stockCount": stock_count,
                "stockIndexSha256": digest(stock_index), "stockLogicalSha256": digest(stock_logical),
                "outputSize": len(raw), "outputSha256": digest(raw),
                "appendedCount": len(appended), "appendedIndexSize": len(extra_index),
                "payload": "payload/" + relative, "payloadSize": len(insert),
                "payloadSha256": digest(insert)})

        explosion = json.loads((SOURCES[0][2] / "report.json").read_text())
        ground_base = json.loads((ROOT / "analysis/liquid-bundle-v2-trial-24735202/report.json").read_text())
        ground_wheel = json.loads((ROOT / "analysis/liquid-hue-wheel-24735202/report.json").read_text())
        inputs = [(ROOT / "analysis/hue-wheel-bundle-24735202", row["path"], row["sha256"], row["bytes"])
                  for row in explosion["added_material_streams"]]
        inputs += [(ROOT / "analysis/liquid-bundle-v2-trial-24735202", row["stream"], row["sha256"], row["bytes"])
                   for row in ground_base["added_assets"] if row["kind"] == "material"]
        inputs += [(ROOT / "analysis/liquid-hue-wheel-24735202", row["stream"], row["sha256"], row["bytes"])
                   for row in ground_wheel["added_material_streams"]]
        if len(inputs) != 1098:
            raise ValueError("Expected thirteen explosion and 1,085 ground material streams")
        for folder, target, expected_sha, expected_size in sorted(inputs, key=lambda row: row[1]):
            if not target.startswith("bundle/data/rb/"):
                raise ValueError("Unexpected material stream destination")
            source = (folder / target).read_bytes()
            if len(source) != expected_size or digest(source) != expected_sha:
                raise ValueError("Authored stream provenance changed: " + target)
            payload = "payload/materials/" + target.rsplit("/", 1)[-1]
            put(tmp, payload.removeprefix("payload/"), source)
            manifest["streams"].append({"target": target, "payload": payload,
                                         "size": expected_size, "sha256": expected_sha})
        if len({row["target"] for row in manifest["streams"]}) != len(inputs):
            raise ValueError("Repeated custom material destination")
        for relative in ("RainbowBarrels.mod", "scripts/mods/RainbowBarrels/RainbowBarrels.lua",
                         "scripts/mods/RainbowBarrels/RainbowBarrels_data.lua",
                         "scripts/mods/RainbowBarrels/RainbowBarrels_localization.lua"):
            data = (ROOT / relative).read_bytes()
            manifest["modFiles"].append({"target": "mods/RainbowBarrels/" + relative,
                                         "payload": "RainbowBarrels/" + relative,
                                         "size": len(data), "sha256": digest(data)})
        put(tmp, "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
        os.replace(tmp, OUTPUT)
        print(json.dumps({"version": VERSION, "bundles": len(manifest["bundles"]),
                          "streams": len(manifest["streams"]),
                          "bundle_payload_bytes": sum(row["payloadSize"] for row in manifest["bundles"]),
                          "status": "authenticated custom additions only; stock bundles excluded"}, indent=2))
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
