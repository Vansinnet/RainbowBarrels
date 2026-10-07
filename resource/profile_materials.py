"""Keep exact stock material streams and a bounded color-control inventory."""

import hashlib
import importlib
import json
from pathlib import Path
import sys

from resolve_materials import ROOT, resolve


OUT = Path(__file__).resolve().parents[1] / "analysis" / "stock-materials-24735202"


def main():
    if OUT.exists():
        raise ValueError("Research directory already exists; use a fresh location")
    results = resolve()
    if len(results) != 10 or any(len(row.get("streams", [])) != 1 for row in results):
        raise ValueError("Expected ten identified material streams")
    sys.path.insert(0, str(ROOT / "docs/analysis-flame-target-20260917-a1"))
    parser = importlib.import_module("parse_materials")
    records = []
    payloads = {}
    for row in results:
        item = row["streams"][0]
        if item["installed_status"] not in ("verified stock", "not managed by RainbowFlame"):
            raise ValueError("Modified game material cannot be an input")
        data = Path(item["path"]).read_bytes()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Material source changed during research")
        parsed = parser.parse(data)
        name = row["material_hash"] + ".material"
        payloads[name] = data
        records.append({"identity": row["material_hash"], "game_source": item["path"],
                        "source_sha256": item["sha256"], "source_bytes": len(data),
                        "status": item["installed_status"], "material_file": name,
                        "parents": parsed["parent_hashes"], "shader_size": parsed["shader_size"],
                        "textures": parsed["textures"],
                        "variables": [{"hash": v["name_hash"], "type": v.get("type"),
                                       "value": v.get("value")} for v in parsed["variables"]]})
    OUT.mkdir(parents=True)
    for name, data in payloads.items():
        (OUT / name).write_bytes(data)
    (OUT / "provenance.json").write_text(json.dumps({"build": "24735202",
                                                  "exe_version": "1.3.770.210",
                                                  "status": "offline research; no installed writes",
                                                  "materials": records}, indent=2) + "\n")
    print(json.dumps([{k: row[k] for k in ("identity", "status", "parents", "shader_size")}
                      | {"variables": row["variables"]} for row in records], indent=2))


if __name__ == "__main__":
    main()
