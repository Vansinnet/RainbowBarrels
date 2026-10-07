"""Read-only preflight for the candidate installer after dev-file rollback."""

import json
from pathlib import Path

from deploy_test import GAME, ROOT, nonredirected, sha


def main():
    manifest = json.loads((ROOT / "payload/manifest.json").read_text())
    blockers = []
    for entry in manifest["bundles"]:
        target = GAME / entry["target"]
        nonredirected(target)
        if (not target.is_file() or target.stat().st_size != entry["stockSize"]
                or sha(target.read_bytes()) != entry["stockSha256"]):
            blockers.append({"target": entry["target"], "reason": "not supported stock"})
    for entry in manifest["streams"] + manifest["modFiles"]:
        target = GAME / entry["target"]
        nonredirected(target)
        if target.exists() or target.is_symlink():
            blockers.append({"target": entry["target"], "reason": "added target occupied"})
    order = (GAME / "mods/mod_load_order.txt").read_bytes()
    if any(line.strip(b"\r\n") == b"RainbowBarrels" for line in order.splitlines()):
        blockers.append({"target": "mods/mod_load_order.txt", "reason": "old RainbowBarrels line"})
    print(json.dumps({"game_root": str(GAME), "stock_bundles": len(manifest["bundles"]),
                      "unoccupied_added_targets": len(manifest["streams"]) + len(manifest["modFiles"]),
                      "blockers": blockers,
                      "status": "read-only RC input preflight; no game files changed"}, indent=2))


if __name__ == "__main__":
    main()
