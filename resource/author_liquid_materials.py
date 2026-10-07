"""Author three isolated persistent-fire material shaders with scalar hue exports."""

import hashlib
import json
from pathlib import Path

import author_full_materials as full
import author_material_families as fitted


ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "analysis/liquid-stock-24735202"
SHADERS = ROOT / "analysis/liquid-hue-programs-24735202"
OUT = ROOT / "analysis/liquid-hue-materials-24735202"
SHADER_MATERIALS = {"4cd51280796476b3", "1cc58f33452ca960", "62c7bb3aa1cac9c2"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if OUT.exists():
        raise ValueError("Output already exists")
    stocks = {item["identity"]: item for item in json.loads(
        (STOCK / "materials-provenance.json").read_text())["materials"]}
    programs = json.loads((SHADERS / "provenance.json").read_text())["programs"]
    result = []
    payloads = {}
    full.PROFILES["62c7bb3aa1cac9c2"] = (19, 112, 128)
    for name in sorted(SHADER_MATERIALS):
        item = stocks[name]
        source = (STOCK / "materials" / item["retained_file"]).read_bytes()
        if sha(source) != item["stream_sha256"]:
            raise ValueError("Stock material changed: " + name)
        matches = [p for p in programs if p["program"].startswith(name + "-")]
        if not matches or len({p["export_offset"] for p in matches}) != 1:
            raise ValueError("Unverified new scalar register: " + name)
        replacements = {}
        for row in matches:
            data = (SHADERS / (row["program"] + ".dxbc")).read_bytes()
            if sha(data) != row["authored_sha256"]:
                raise ValueError("Compiled shader changed")
            previous = replacements.setdefault(row["source_sha256"], data)
            if previous != data:
                raise ValueError("Conflicting shader program identity")
        if name in full.PROFILES:
            if matches[0]["export_offset"] != 112:
                raise ValueError("Stock material buffer size/reflection")
            candidate, summary = full.author(source, name, replacements)
        else:
            candidate, summary = fitted.author(source, name, matches[0]["export_offset"], replacements)
        result.append(summary)
        payloads[name + ".material"] = candidate
    if len(result) != 3:
        raise ValueError("Incomplete liquid-fire material graph")
    OUT.mkdir(parents=True)
    for filename, data in payloads.items():
        (OUT / filename).write_bytes(data)
    (OUT / "provenance.json").write_text(json.dumps({"build": "24735202",
                                                  "status": "offline candidates; unregistered and untested in game",
                                                  "materials": result}, indent=2) + "\n")
    print(json.dumps([{"material": item["material"], "changed_pixel_programs": len(item["changed_programs"]),
                      "registration_groups": item["registered_groups"],
                      "candidate_sha256": item["candidate_sha256"]} for item in result], indent=2))


if __name__ == "__main__":
    main()
