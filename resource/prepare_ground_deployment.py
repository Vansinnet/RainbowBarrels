"""Read-only preflight for a second, separately approved liquid-fire game test."""

import hashlib
import json
from pathlib import Path
import re

from analyze_effects import GAME, decode_bundle_parts, decoder
from build_green_bundle import bundle


ROOT = Path(__file__).resolve().parents[1]
LIQUID = ROOT / "analysis/liquid-bundle-trial-24735202"
EXISTING = ROOT / "analysis/deployment-runs/20260923T074518Z-ac639c88"
OUT = ROOT / "analysis/ground-deployment-preflight-24735202"
GAME_BUNDLE = GAME / "bundle/b224998193576995"
STOCK = "775762aae54cfd5313856f8b097e2527774600e92df896d375e4af6b8916376d"
PREVIOUS_EXPLOSION = "a0a15fcde68bbd2d7a4ec0cd998bd7d143d2999d3d0b8a74baa60340b529cff9"
MOD_FILES = (
    "scripts/mods/RainbowBarrels/RainbowBarrels.lua",
    "scripts/mods/RainbowBarrels/RainbowBarrels_localization.lua",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def nonredirected(path):
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise ValueError("Redirected game target: " + str(path))


def main():
    if OUT.exists():
        raise ValueError("Ground preflight output exists; choose a fresh location")
    steam = (GAME.parent.parent / "appmanifest_1361210.acf").read_text()
    build = re.search(r'"buildid"\s*"(\d+)"', steam)
    if not build or build[1] != "24735202":
        raise ValueError("Unsupported Steam build")
    old_receipt = json.loads((EXISTING / "receipt.json").read_text())
    if old_receipt["state"] != "candidate_installed" or old_receipt["installed_sha256"] != PREVIOUS_EXPLOSION:
        raise ValueError("Explosion candidate is no longer the owned installed version")
    if sha((GAME / "bundle/98bb14b1d247a0c8").read_bytes()) != PREVIOUS_EXPLOSION:
        raise ValueError("Previous explosion resource changed")
    load_order = GAME / "mods/mod_load_order.txt"
    nonredirected(load_order)
    current_order = load_order.read_bytes()
    entries = [line.strip() for line in current_order.decode("utf-8-sig").splitlines()]
    if entries.count("RainbowBarrels") != 1:
        raise ValueError("Vortex-managed load order no longer has exactly one RainbowBarrels entry")
    for parent in (GAME, GAME / "bundle", GAME / "bundle/data", GAME / "bundle/data/rb",
                   GAME / "mods", GAME / "mods/RainbowBarrels"):
        nonredirected(parent)
        if not parent.is_dir():
            raise ValueError("Missing game resource/mod directory")
    for item in old_receipt["resources"]:
        path = GAME / item["relative"]
        nonredirected(path)
        if sha(path.read_bytes()) != item["sha256"]:
            raise ValueError("Previous owned stream changed")
    nonredirected(GAME_BUNDLE)
    raw = GAME_BUNDLE.read_bytes()
    if sha(raw) != STOCK:
        raise ValueError("Original persistent-fire bundle is not stock")
    records, padding = decode_bundle_parts(raw, decoder())
    unchanged = bundle([identity for identity, _, _ in records], [record for _, record, _ in records],
                       raw[12:268], padding)
    parsed, rest = decode_bundle_parts(unchanged, lambda block: block)
    if parsed != records or rest != padding:
        raise ValueError("No-op package record/padding preservation")
    report = json.loads((LIQUID / "report.json").read_text())
    candidate = (LIQUID / "bundle/b224998193576995").read_bytes()
    if (report["source_bundle_sha256"] != STOCK
            or sha(unchanged) != report["noop_bundle_sha256"]
            or sha(candidate) != report["candidate_bundle_sha256"]):
        raise ValueError("Offline candidate identity changed")
    materials = []
    for item in report["added_assets"]:
        if item["kind"] != "material":
            continue
        path = item["stream"]
        target = GAME / path
        nonredirected(target)
        if target.exists():
            raise ValueError("New persistent-fire stream already installed")
        payload = (LIQUID / path).read_bytes()
        if sha(payload) != item["sha256"] or len(payload) != item["bytes"]:
            raise ValueError("Offline persistent-fire stream identity")
        materials.append({"relative": path, "sha256": item["sha256"], "bytes": item["bytes"]})
    if len(materials) != 5:
        raise ValueError("Expected five additive liquid-fire streams")
    previously_deployed = {row["relative"]: row for row in old_receipt["mod_files"]}
    changed_mod = []
    for relative in MOD_FILES:
        deployed = GAME / "mods/RainbowBarrels" / relative
        nonredirected(deployed)
        old = previously_deployed.get("mods/RainbowBarrels/" + relative)
        data = (ROOT / relative).read_bytes()
        if not old or sha(deployed.read_bytes()) != old["sha256"] or sha(data) == old["sha256"]:
            raise ValueError("Deployed/source Lua version mismatch for focused update")
        changed_mod.append({"relative": "mods/RainbowBarrels/" + relative,
                            "deployed_sha256": old["sha256"], "new_sha256": sha(data),
                            "new_bytes": len(data)})
    manifest = {"steam_build": build[1], "game_root": str(GAME),
                "status": "read-only preflight; no new game-file writes",
                "existing_run": str(EXISTING), "previous_explosion_sha256": PREVIOUS_EXPLOSION,
                "liquid_bundle": "bundle/b224998193576995", "stock_sha256": STOCK,
                "noop_sha256": sha(unchanged), "noop_bytes": len(unchanged),
                "candidate_sha256": sha(candidate), "candidate_bytes": len(candidate),
                "new_streams": materials, "changed_mod_files": changed_mod,
                "load_order_sha256": sha(current_order),
                "external_load_order_drift": sha(current_order) != old_receipt["load_order_after_sha256"],
                "rollback": "Close game, restore exact original b224 bundle and prior deployed Lua files from unique backups; remove only five exact owned streams. Leave b98 bundle, thirteen prior streams and Vortex load order untouched."}
    OUT.mkdir(parents=True)
    (OUT / "b224998193576995.noop.bundle").write_bytes(unchanged)
    (OUT / "preflight.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({key: manifest[key] for key in ("stock_sha256", "noop_sha256", "candidate_sha256",
                                                    "previous_explosion_sha256", "load_order_sha256",
                                                    "external_load_order_drift", "status")}, indent=2))


if __name__ == "__main__":
    main()
