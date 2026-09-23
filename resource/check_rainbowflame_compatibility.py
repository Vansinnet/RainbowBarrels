"""Read-only exact resource target comparison with RainbowFlame's release manifest."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLAME = ROOT.parent / "RainbowFlame"


def main():
    barrels = json.loads((ROOT / "payload/manifest.json").read_text())
    flame = json.loads((FLAME / "payload/manifest.json").read_text())
    mine = {item["target"].casefold() for collection in ("bundles", "streams", "modFiles")
            for item in barrels[collection]}
    theirs = {item["target"].casefold() for item in flame["files"]}
    shared = sorted(mine & theirs)
    if barrels["steamBuild"] != flame["steamBuild"] or barrels["exeVersion"] != flame["exeVersion"]:
        raise ValueError("Different supported game builds")
    report = {"barrels_managed_files": len(mine), "flame_managed_files": len(theirs),
              "shared_targets": shared, "shared_target_count": len(shared),
              "same_game_build": True,
              "status": "offline manifest targets only; loader, VFX and simultaneous game runtime not established"}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
