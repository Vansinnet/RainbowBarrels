"""Read-only deployment preflight and no-op bundle construction for one game build."""

import hashlib
import json
from pathlib import Path
import re

from analyze_effects import GAME, SOURCES, decode_bundle_parts, decoder
from build_green_bundle import bundle


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "analysis/hue-wheel-bundle-24735202"
OUT = ROOT / "analysis/deployment-preflight-24735202"
STOCK = "9086f577b55278286bc5cd72de529300d61ba15d2612ad66a1cbe8b272d4da48"
LUA = (
    "RainbowBarrels.mod",
    "scripts/mods/RainbowBarrels/RainbowBarrels.lua",
    "scripts/mods/RainbowBarrels/RainbowBarrels_data.lua",
    "scripts/mods/RainbowBarrels/RainbowBarrels_localization.lua",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if OUT.exists():
        raise ValueError("Preflight already exists; use a unique analysis directory")
    steam = (GAME.parent.parent / "appmanifest_1361210.acf").read_text()
    match = re.search(r'"buildid"\s*"(\d+)"', steam)
    if not match or match[1] != "24735202":
        raise ValueError("Unsupported Steam game build")
    source = GAME / SOURCES[1][0]
    if not source.is_file() or source.is_symlink():
        raise ValueError("Stock target missing or redirected")
    stock = source.read_bytes()
    if sha(stock) != STOCK:
        raise ValueError("Stock bundle hash changed")
    records, padding = decode_bundle_parts(stock, decoder())
    noop = bundle([identity for identity, _, _ in records], [raw for _, raw, _ in records],
                  stock[12:268], padding)
    reread, final_padding = decode_bundle_parts(noop, lambda block: block)
    if reread != records or final_padding != padding:
        raise ValueError("No-op physical reconstruction changed logical resources")
    authored = json.loads((CANDIDATE / "report.json").read_text())
    candidate = (CANDIDATE / SOURCES[1][0]).read_bytes()
    if (authored["stock_bundle_sha256"] != STOCK
            or sha(candidate) != authored["candidate_bundle_sha256"]):
        raise ValueError("Candidate bundle identity")
    additions = []
    for item in authored["added_material_streams"]:
        relative = item["path"]
        if not relative.startswith("bundle/data/rb/") or len(relative) != len("bundle/data/rb/") + 16:
            raise ValueError("Unexpected game output path")
        payload = (CANDIDATE / relative).read_bytes()
        if sha(payload) != item["sha256"] or len(payload) != item["bytes"]:
            raise ValueError("Authored stream identity")
        destination = GAME / relative
        if destination.exists() or destination.is_symlink():
            raise ValueError("Resource addition already exists: " + relative)
        additions.append({"relative": relative, "bytes": len(payload), "sha256": sha(payload)})
    if len(additions) != 13:
        raise ValueError("Missing new material stream")
    if (GAME / "bundle/data/rb").exists() or (GAME / "bundle/data/rb").is_symlink():
        raise ValueError("Generated stream directory already exists")
    target_mod = GAME / "mods/RainbowBarrels"
    if target_mod.exists() or target_mod.is_symlink():
        raise ValueError("Deployed mod folder already exists")
    contents = []
    for name in LUA:
        data = (ROOT / name).read_bytes()
        contents.append({"relative": "mods/RainbowBarrels/" + name,
                         "bytes": len(data), "sha256": sha(data)})
    order_path = GAME / "mods/mod_load_order.txt"
    if order_path.is_symlink():
        raise ValueError("Load order is redirected")
    order = order_path.read_bytes()
    if "RainbowBarrels" in order.decode("utf-8-sig").splitlines():
        raise ValueError("RainbowBarrels already present in load order")
    report = {"steam_build": match[1], "game_root": str(GAME),
              "status": "read-only preflight; no game writes or runtime result",
              "replaced_stock_bundle": SOURCES[1][0], "stock_bundle_sha256": STOCK,
              "stock_bundle_bytes": len(stock), "noop_stored_sha256": sha(noop),
              "noop_stored_bytes": len(noop),
              "candidate_bundle_sha256": sha(candidate), "candidate_bundle_bytes": len(candidate),
              "new_game_resources": additions, "deployed_mod_files": contents,
              "load_order_sha256": sha(order), "load_order_bytes": len(order),
              "load_order_managed_by_vortex": b"managed by Vortex" in order,
              "rollback": "Restore only the SHA-pinned original bundle from the unique deployment backup; remove exact owned additions and restore exact pre-test load-order bytes. Refuse if any deployed file changed unexpectedly."}
    OUT.mkdir(parents=True)
    (OUT / "98bb14b1d247a0c8.noop.bundle").write_bytes(noop)
    (OUT / "preflight.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("steam_build", "stock_bundle_sha256",
                                                  "noop_stored_sha256", "candidate_bundle_sha256",
                                                  "load_order_managed_by_vortex", "status")}, indent=2))


if __name__ == "__main__":
    main()
