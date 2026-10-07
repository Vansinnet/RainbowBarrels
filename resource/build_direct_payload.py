"""Prepare the pinned, installer-free RainbowBarrels resources from local verified candidates."""

import argparse
import hashlib
import json
from pathlib import Path


MOD = Path(__file__).resolve().parents[1]
LIBRARY_BLOB = "0e0e788c7ae9f523a1a163e711b2e1a86a016cfc"
DLL_BLOB = "0267e09bc60ad50218aafd0680eb1839e49b4c44"
CANDIDATES = {
    "explosion": MOD / "analysis/hue-wheel-bundle-24735202/bundle/98bb14b1d247a0c8",
    "ground": MOD / "analysis/liquid-floor-graph-trial-24735202/bundle/b224998193576995",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--polychromatic", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((MOD / "payload/manifest.json").read_text(encoding="utf-8"))
    if manifest["product"] != "RainbowBarrels" or manifest["version"] != "1.0.0" or manifest["steamBuild"] != "24735202":
        raise ValueError("Unexpected source manifest")

    outputs = {}
    for entry in manifest["bundles"]:
        name = entry["target"].removeprefix("bundle/")
        if entry["id"] not in CANDIDATES or name != CANDIDATES[entry["id"]].name:
            raise ValueError(f"Unexpected bundle: {entry['id']}")
        data = CANDIDATES[entry["id"]].read_bytes()
        if len(data) != entry["outputSize"] or sha256(data) != entry["outputSha256"]:
            raise ValueError(f"Authored bundle changed: {name}")
        outputs[MOD / "payload/bundles" / name] = data
    if len(outputs) != 2:
        raise ValueError("Expected both authored bundles")

    material_names = []
    for entry in manifest["streams"]:
        target = entry["target"]
        if not target.startswith("bundle/data/rb/"):
            raise ValueError(f"Unexpected material target: {target}")
        name = target.removeprefix("bundle/data/rb/")
        if len(name) != 16 or any(char not in "0123456789abcdef" for char in name):
            raise ValueError(f"Invalid material name: {name}")
        if entry["payload"] != "payload/materials/" + name:
            raise ValueError(f"Unexpected material payload: {name}")
        data = (MOD / entry["payload"]).read_bytes()
        if len(data) != entry["size"] or sha256(data) != entry["sha256"]:
            raise ValueError(f"Material has changed: {name}")
        material_names.append(name)
    if len(material_names) != 1098 or len(set(material_names)) != len(material_names):
        raise ValueError("Expected 1098 distinct material streams")
    if {path.name for path in (MOD / "payload/materials").iterdir()} != set(material_names):
        raise ValueError("Material directory does not match authenticated manifest")
    outputs[MOD / "scripts/mods/RainbowBarrels/redirect_files.lua"] = (
        "return {\n" + "".join(f'    "{name}",\n' for name in material_names) + "}\n"
    ).encode("ascii")

    other = args.polychromatic
    external = (
        (other / "scripts/mods/Polychromatic/asset_redirect.lua", MOD / "scripts/mods/RainbowBarrels/asset_redirect.lua", LIBRARY_BLOB),
        (other / "bin/asset-redirect.dll", MOD / "bin/asset-redirect.dll", DLL_BLOB),
    )
    for source, destination, expected in external:
        data = source.read_bytes()
        if git_blob(data) != expected:
            raise ValueError(f"Unexpected Asset Redirect component: {source}")
        outputs[destination] = data

    for destination, data in outputs.items():
        if destination.exists() and destination.read_bytes() != data:
            raise ValueError(f"Existing output differs: {destination}")
    for destination, data in outputs.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(data)
        print(f"Verified {destination.relative_to(MOD)}: {len(data)} bytes")
    print(f"Verified 2 authored bundles and {len(material_names)} material streams")


if __name__ == "__main__":
    main()
