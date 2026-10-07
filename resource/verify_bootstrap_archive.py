"""Check and extract the automatic-setup candidate, never an installed game."""
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile

root = Path(__file__).resolve().parents[1]
archive = Path(sys.argv[1]).resolve()
extract = Path(sys.argv[2]).resolve()
if extract.exists() or not extract.parent.is_dir():
    raise ValueError("Extraction destination must be new, with an existing approved parent")
layout = json.loads((root / "release-layout.json").read_text(encoding="utf-8"))
expected = {}
for category in layout["package"].values():
    for entry in category:
        source = root / entry["source"]
        if source.is_dir():
            for path in source.rglob("*"):
                if path.is_file():
                    expected[entry["destination"] + "/" + path.relative_to(source).as_posix()] = path
        else:
            expected[entry["destination"]] = source
expected["RainbowBarrels/RainbowBarrels.Setup.exe"] = None
recipes = json.loads((root / "bootstrap/RainbowBarrels.Setup/manifest.json").read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
with ZipFile(archive) as z:
    names = z.namelist()
    assert len(names) == len(expected) + 1 and set(names) == set(expected) | {"SHA256SUMS"}
    assert not any(name.lower().endswith(".dll") or "asset_redirect" in name for name in names)
    sums = {name: digest.lower() for digest, name in
            (line.split("  ", 1) for line in z.read("SHA256SUMS").decode("ascii").splitlines())}
    assert set(sums) == set(expected)
    for name, path in expected.items():
        assert "\\" not in name and ".." not in Path(name).parts
        data = z.read(name)
        assert sha(data) == sums[name], name
        if path is not None:
            assert data == path.read_bytes(), name
    for item in recipes["files"]:
        data = z.read("RainbowBarrels/" + item["payload"])
        assert len(data) == item["size"] and sha(data) == item["sha256"]
    digest, filename = archive.with_suffix(".zip.sha256").read_text().strip().split("  ", 1)
    assert filename == archive.name and digest.lower() == sha(archive.read_bytes())
    z.extractall(extract)
print(f"Verified {len(names)} archive entries, 1100 embedded recipes, SHA256SUMS and ZIP hash.")
print(f"Archive SHA-256: {sha(archive.read_bytes())}")
print(f"Helper SHA-256: {sums['RainbowBarrels/RainbowBarrels.Setup.exe']}")
print(f"Extraction: {extract}")
