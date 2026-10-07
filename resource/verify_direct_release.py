"""Verify every ZIP entry against the pinned material and release source manifests."""

import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile


mod = Path(__file__).resolve().parents[1]
archive = Path(sys.argv[1]).resolve()
layout = json.loads((mod / "release-layout.json").read_text(encoding="utf-8"))
old_manifest = json.loads((mod / "payload/manifest.json").read_text(encoding="utf-8"))
assert layout["profile"] == "direct" and len(old_manifest["streams"]) == 1098
expected = {}
for category in layout["package"].values():
    for entry in category:
        source, destination = entry["source"], entry["destination"]
        if source == "payload/materials":
            for material in old_manifest["streams"]:
                file = material["payload"]
                expected[f"{destination}/{Path(file).name}"] = file
        else:
            expected[destination] = source

source_lines = (archive.parent / "RainbowBarrels.source.sha256").read_text(encoding="ascii").splitlines()
sources = {name: digest.lower() for digest, name in (line.split("  ", 1) for line in source_lines)}
assert len(expected) == 1113
assert set(sources) == {f"RainbowBarrels/{source}" for source in expected.values()} | {"RainbowBarrels/release-layout.json"}
assert len(sources) == len(expected) + 1
with ZipFile(archive) as z:
    names = z.namelist()
    assert len(names) == len(expected) and set(names) == set(expected)
    for name, source in expected.items():
        assert name.startswith("RainbowBarrels/") and "\\" not in name and ".." not in Path(name).parts
        digest = hashlib.sha256(z.read(name)).hexdigest()
        assert digest == sources[f"RainbowBarrels/{source}"], name
        assert digest == hashlib.sha256((mod / source).read_bytes()).hexdigest(), name

hash_line = (archive.parent / "RainbowBarrels.zip.sha256").read_text(encoding="ascii").strip()
digest, filename = hash_line.split("  ", 1)
assert filename == archive.name and digest.lower() == hashlib.sha256(archive.read_bytes()).hexdigest()
assert json.loads((mod / "info.json").read_text(encoding="utf-8"))["version"] == "1.1.0"
print(f"Verified {len(names)} archive entries against source manifest; ZIP SHA-256 {digest}")
