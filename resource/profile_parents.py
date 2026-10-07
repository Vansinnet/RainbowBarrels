"""Resolve the three parent shaders referenced by barrel child materials."""

import hashlib
import json
from pathlib import Path
import re
import struct

from analyze_effects import GAME, OUT, SOURCES, decode_bundle, decoder
from inspect_stock import murmur64


ROOT = Path(__file__).resolve().parents[4]
MATERIALS = Path(__file__).resolve().parents[1] / "analysis" / "stock-materials-24735202"
OUT_PARENTS = Path(__file__).resolve().parents[1] / "analysis" / "stock-parents-24735202"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if OUT_PARENTS.exists():
        raise ValueError("Parent research already exists; choose a fresh location")
    provenance = json.loads((MATERIALS / "provenance.json").read_text())
    parents = {p for material in provenance["materials"] for p in material["parents"]
               if p != "0000000000000000"}
    if len(parents) != 3:
        raise ValueError("Unexpected parent count")
    source = GAME / SOURCES[1][0]
    particle_evidence = json.loads((OUT / "provenance.json").read_text())
    expected_sha = next(p["source_sha256"] for p in particle_evidence["particles"]
                        if p["game_source"] == str(source))
    data = source.read_bytes()
    if sha(data) != expected_sha:
        raise ValueError("Source package identity changed")
    records = decode_bundle(data, decoder())
    managed = {row["target"].lower(): row for row in json.loads(
        (ROOT / "mods/active/RainbowFlame/payload/manifest.json").read_text())["files"]}
    result = []
    extracted = {}
    for parent in sorted(parents):
        matches = [(i, raw) for i, (identity, raw, _) in enumerate(records)
                   if identity[:2] == (murmur64("material"), int(parent, 16))]
        if len(matches) != 1:
            result.append({"parent": parent, "matches": len(matches), "in_package": False})
            continue
        index, raw = matches[0]
        references = re.findall(rb"data/[0-9a-f]{2}/[0-9a-f]{16}", raw)
        if len(references) != 1:
            raise ValueError("Expected one external material stream")
        relative = "bundle/" + references[0].decode()
        path = GAME / relative
        content = path.read_bytes()
        manifest = managed.get(relative)
        status = ("verified stock" if manifest and sha(content) == manifest["baseSha256"]
                  else "RainbowFlame replacement" if manifest and sha(content) == manifest["outputSha256"]
                  else "unexpected managed file" if manifest else "not managed by RainbowFlame")
        if status not in ("verified stock", "not managed by RainbowFlame"):
            raise ValueError("A parent material is not a verified stock candidate")
        version, mo, ms, so, ss, tail, ts = struct.unpack_from("<7I", content)
        extracted[parent + ".material"] = content
        result.append({"parent": parent, "resource_index": index,
                       "resource_sha256": sha(raw), "stream": str(path),
                       "bytes": len(content), "sha256": sha(content), "status": status,
                       "extracted_file": parent + ".material",
                       "version": version, "shader_size": ss,
                       "layout": [mo, ms, so, tail, ts]})
    if len(extracted) != 3:
        raise ValueError("Missing parent material")
    OUT_PARENTS.mkdir(parents=True)
    for filename, data in extracted.items():
        (OUT_PARENTS / filename).write_bytes(data)
    (OUT_PARENTS / "provenance.json").write_text(json.dumps({"build": "24735202",
                                                         "status": "offline stock research; no installed writes",
                                                         "parents": result}, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
