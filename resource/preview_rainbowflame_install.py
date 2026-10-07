"""Read-only stock-target preflight for separate RainbowFlame 1.2.0 installation."""

import json
from pathlib import Path

from deploy_test import GAME, ROOT, nonredirected, sha


FLAME = ROOT.parent / "RainbowFlame"


def main():
    manifest = json.loads((FLAME / "payload/manifest.json").read_text())
    if manifest["product"] != "RainbowFlame" or manifest["version"] != "1.2.0":
        raise ValueError("Unexpected companion manifest")
    checked = 0
    problems = []
    for item in manifest["files"]:
        target = GAME / item["target"]
        nonredirected(target)
        if item["addition"]:
            if target.exists() or target.is_symlink():
                problems.append({"target": item["target"], "reason": "already occupied"})
        else:
            if not target.is_file() or target.stat().st_size != item["baseSize"] or sha(target.read_bytes()) != item["baseSha256"]:
                problems.append({"target": item["target"], "reason": "not pristine stock"})
        if item.get("base"):
            basis = GAME / item["base"]
            nonredirected(basis)
            if (not basis.is_file() or basis.stat().st_size != item["baseSize"]
                    or sha(basis.read_bytes()) != item["baseSha256"]):
                problems.append({"target": item["base"], "reason": "authenticated delta input changed"})
        checked += 1
    print(json.dumps({"game_root": str(GAME), "product": "RainbowFlame", "version": "1.2.0",
                      "release_targets_checked": checked, "blockers": problems,
                      "status": "read-only game/payload preflight; no game changes"}, indent=2))


if __name__ == "__main__":
    main()
