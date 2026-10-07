"""Retain only five identified stock liquid-fire material streams for offline research."""

import hashlib
import json
from pathlib import Path

from resolve_liquid_materials import OUT, SOURCE_SHA, resolve


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    destination = OUT / "materials"
    report = OUT / "materials-provenance.json"
    if destination.exists() or report.exists():
        raise ValueError("Stock material research already retained")
    rows = resolve()
    if len(rows) != 5 or any(row.get("status") not in ("verified stock", "not managed by RainbowFlame")
                             for row in rows):
        raise ValueError("Modified or incomplete source material graph")
    payloads = {}
    for row in rows:
        path = Path(row["stream"])
        data = path.read_bytes()
        if len(data) != row["stream_bytes"] or sha(data) != row["stream_sha256"]:
            raise ValueError("Source stream identity drift")
        filename = row["identity"] + ".material"
        row["retained_file"] = filename
        payloads[filename] = data
    destination.mkdir()
    for name, data in payloads.items():
        (destination / name).write_bytes(data)
    report.write_text(json.dumps({"build": "24735202", "source_bundle_sha256": SOURCE_SHA,
                                  "status": "offline stock research; no installed write",
                                  "materials": rows}, indent=2) + "\n")
    print(json.dumps([{"material": row["identity"], "shader_bytes": row["shader_bytes"],
                      "source_sha256": row["stream_sha256"], "parents": row["parents"]}
                      for row in rows], indent=2))


if __name__ == "__main__":
    main()
