"""Extract three narrowly named stock liquid-fire particle records for research."""

import hashlib
import json
from pathlib import Path

from analyze_effects import GAME, decode_bundle_parts, decoder
from inspect_liquid_stock import LIQUID_EFFECTS
from inspect_stock import murmur64


OUT = Path(__file__).resolve().parents[1] / "analysis/liquid-stock-24735202"
SOURCES = {
    "6e2428a96f7ba327": (LIQUID_EFFECTS[0],),
    "ee15538490f76052": (LIQUID_EFFECTS[1],),
    "b224998193576995": LIQUID_EFFECTS,
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if OUT.exists():
        raise ValueError("Research output exists; use a fresh location")
    unpack = decoder()
    payloads, reports = {}, []
    for package, effects in SOURCES.items():
        path = GAME / "bundle" / package
        source = path.read_bytes()
        records, padding = decode_bundle_parts(source, unpack)
        for effect in effects:
            matches = [(index, identity, raw, descriptors)
                       for index, (identity, raw, descriptors) in enumerate(records)
                       if identity[:2] == (murmur64("particles"), murmur64(effect))]
            if len(matches) != 1:
                raise ValueError("Particle identity count: " + effect)
            index, identity, raw, descriptors = matches[0]
            filename = f"{package}-{Path(effect).name}.particles"
            payloads[filename] = raw
            reports.append({"effect": effect, "bundle": str(path),
                            "bundle_sha256": sha(source), "bundle_bytes": len(source),
                            "resource_count": len(records), "record_index": index,
                            "mode": identity[2], "descriptors": descriptors,
                            "file": filename, "record_sha256": sha(raw),
                            "record_bytes": len(raw),
                            "decoded_padding_nonzero": sum(bool(byte) for byte in padding)})
    for effect in LIQUID_EFFECTS:
        sources = [item["record_sha256"] for item in reports if item["effect"] == effect]
        if len(sources) != 2 or sources[0] != sources[1]:
            raise ValueError("Standalone and shared liquid stock particle disagree")
    OUT.mkdir(parents=True)
    for name, data in payloads.items():
        (OUT / name).write_bytes(data)
    (OUT / "provenance.json").write_text(json.dumps({"build": "24735202",
                                                  "status": "offline, read-only installed stock extraction",
                                                  "particles": reports}, indent=2) + "\n")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
