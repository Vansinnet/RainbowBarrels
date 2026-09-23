"""Independent final ZIP, embedded SHA256SUMS, and resource-payload audit."""

import hashlib
import json
from pathlib import Path
import sys
import zipfile


EXPECTED_BUNDLES = {
    "bundle/98bb14b1d247a0c8": "a0a15fcde68bbd2d7a4ec0cd998bd7d143d2999d3d0b8a74baa60340b529cff9",
    "bundle/b224998193576995": "7181ef9b900ad89bd5d43759c28f027fc3dbf9b2de68d0ff7beaa798c1900820",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if len(sys.argv) != 2:
        raise ValueError("Usage: python resource/verify_release_archive.py releases/RainbowBarrels.zip")
    archive = Path(sys.argv[1]).resolve()
    record = archive.with_name(archive.name + ".sha256").read_text().split()[0]
    if sha(archive.read_bytes()).lower() != record.lower():
        raise ValueError("Outer archive SHA-256 record")
    with zipfile.ZipFile(archive) as zipfile_reader:
        names = zipfile_reader.namelist()
        if len(names) != len(set(names)) or any("\\" in name or ".." in Path(name).parts for name in names):
            raise ValueError("Unsafe or duplicate ZIP path")
        expected_base = {"RainbowBarrels/RainbowBarrels.mod", "RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua",
                         "RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels_data.lua",
                         "RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels_localization.lua",
                         "README.md", "CHANGELOG.md", "LICENSE", "NOTICE", "SHA256SUMS",
                         "RainbowBarrels.Installer.exe", "RainbowBarrels.Installer.dll",
                         "RainbowBarrels.Installer.deps.json", "RainbowBarrels.Installer.runtimeconfig.json",
                         "payload/manifest.json", "payload/inserts/ground.bin", "payload/inserts/explosion.bin"}
        manifest = json.loads(zipfile_reader.read("payload/manifest.json"))
        if (manifest["product"] != "RainbowBarrels" or manifest["version"] != "1.0.0"
                or manifest["steamBuild"] != "24735202" or manifest["exeVersion"] != "1.3.770.210"):
            raise ValueError("Installer and game version profile")
        actual_bundles = {row["target"]: row["outputSha256"] for row in manifest["bundles"]}
        if actual_bundles != EXPECTED_BUNDLES or len(manifest["streams"]) != 1098:
            raise ValueError("Incomplete authenticated resource recipes")
        expected = expected_base | {row["payload"] for row in manifest["streams"]}
        if set(names) != expected or len(names) != len(expected):
            raise ValueError("Release allowlist or ZIP entry count")
        lines = zipfile_reader.read("SHA256SUMS").decode("ascii").splitlines()
        listed = dict(line.split("  ", 1)[::-1] for line in lines)
        if set(listed) != expected - {"SHA256SUMS"}:
            raise ValueError("Missing or extra SHA256SUMS entries")
        for name in names:
            if name == "SHA256SUMS":
                continue
            if sha(zipfile_reader.read(name)).upper() != listed[name].upper():
                raise ValueError("Packaged file checksum mismatch: " + name)
        for recipe in manifest["bundles"]:
            payload = zipfile_reader.read(recipe["payload"])
            if len(payload) != recipe["payloadSize"] or sha(payload) != recipe["payloadSha256"]:
                raise ValueError("Custom bundle insert payload hash")
            if recipe["stockSha256"] == recipe["outputSha256"] or recipe["stockCount"] >= recipe["stockCount"] + recipe["appendedCount"]:
                raise ValueError("Bundle additions are absent")
        for recipe in manifest["streams"] + manifest["modFiles"]:
            if (len(zipfile_reader.read(recipe["payload"])) != recipe["size"]
                    or sha(zipfile_reader.read(recipe["payload"])) != recipe["sha256"]):
                raise ValueError("Custom file recipe hash")
        if any(name.startswith(("analysis/", "resource/", "installer/", "types/", "LuaExec/")) or
               name.endswith((".pdb", ".pyc", ".bundle")) for name in names):
            raise ValueError("Development or complete extracted game resource in ZIP")
    print(json.dumps({"archive_sha256": record.lower(), "zip_files": len(names),
                      "custom_materials": len(manifest["streams"]), "game_bundles_reconstructed": len(actual_bundles),
                      "sha256sums": len(lines), "status": "release archive allowlist and content hashes passed"}, indent=2))


if __name__ == "__main__":
    main()
