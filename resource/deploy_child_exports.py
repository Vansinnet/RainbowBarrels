"""Hash-pinned two-stream test of persistent-fire child scalar exports."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import GAME, ROOT, RUNS, game_closed, nonredirected, receipt_write, replace_exact, save_new, sha


V2 = ROOT / "analysis/liquid-bundle-v2-trial-24735202"
BUNDLE = "6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d"
LUA = "e80157ec1a7f95423584acbe2cd3eb1307c4ce19619050c239c4bdbf4ac8fc38"
STREAMS = (
    {"relative": "bundle/data/rb/c830ae27aba6f614",
     "previous_sha256": "687e6e6f6b2c54e145cde5930fc8fb710bf2ad7a72bcd39096253deadea0e31a",
     "updated_sha256": "6b36e5b495aff3d258d6044f122ce21354ddc62c6fd322ec7a752947bdbd9190"},
    {"relative": "bundle/data/rb/91db160e1872a6af",
     "previous_sha256": "a62013c26058c8e05c3defcaf5c60af22efa61fd7e27b68e4646c57196cd904c",
     "updated_sha256": "55e69d301287965048bed3c6e689d78f57d1fecc047de5a3659844fe8ceeb6b0"},
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def preflight():
    require(sha((GAME / "bundle/b224998193576995").read_bytes()) == BUNDLE,
            "Installed liquid bundle changed")
    require(sha((GAME / "mods/RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua").read_bytes()) == LUA,
            "Installed Lua fix changed")
    checked = []
    for item in STREAMS:
        target = GAME / item["relative"]
        source = V2 / item["relative"]
        nonredirected(target)
        require(sha(target.read_bytes()) == item["previous_sha256"], "Installed child stream changed")
        require(sha(source.read_bytes()) == item["updated_sha256"], "V2 child stream changed")
        checked.append(dict(item, previous_bytes=target.stat().st_size, updated_bytes=source.stat().st_size))
    order = GAME / "mods/mod_load_order.txt"
    nonredirected(order)
    raw_order = order.read_bytes()
    require(sum(line.strip(b"\r\n") == b"RainbowBarrels" for line in raw_order.splitlines()) == 1,
            "Vortex load order no longer includes exactly one RainbowBarrels")
    return {"steam_build": "24735202", "game_root": str(GAME), "streams": checked,
            "bundle_sha256": BUNDLE, "lua_sha256": LUA,
            "load_order_sha256": sha(raw_order),
            "scope": "read-only two-stream preflight; bundle, Lua and Vortex files stay unchanged"}


def stage():
    game_closed()
    plan = preflight()
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + "-child-exports")
    run.mkdir()
    for item in plan["streams"]:
        save_new(run / Path(item["relative"]).name, (GAME / item["relative"]).read_bytes())
    receipt = {"kind": "child-exports", "game_root": str(GAME), "state": "prepared",
               "streams": plan["streams"], "bundle_sha256": BUNDLE, "lua_sha256": LUA,
               "load_order_sha256_at_stage": plan["load_order_sha256"],
               "rollback": "Close Darktide and restore only the two exact previous child streams with deploy_child_exports.py restore --run <this directory>. Bundle, Lua and Vortex files are not owned by this update."}
    receipt_write(run, receipt)
    for item in receipt["streams"]:
        replace_exact(GAME / item["relative"], (V2 / item["relative"]).read_bytes(), item["previous_sha256"])
    receipt["state"] = "child_exports_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "updated_streams": len(receipt["streams"]),
                      "bundle_lua_and_load_order_unchanged": True}, indent=2))


def restore(run):
    game_closed()
    run = run.resolve()
    require(run.parent == RUNS.resolve() and (run / "receipt.json").is_file(), "Unknown owned child-export run")
    receipt = json.loads((run / "receipt.json").read_text())
    require(receipt["kind"] == "child-exports" and receipt["game_root"] == str(GAME),
            "Wrong child-export receipt")
    for item in receipt["streams"]:
        target = GAME / item["relative"]
        backup = (run / Path(item["relative"]).name).read_bytes()
        require(sha(backup) == item["previous_sha256"], "Previous child backup changed")
        current = sha(target.read_bytes())
        require(current in (item["previous_sha256"], item["updated_sha256"]),
                "Installed child stream changed outside this test")
        if current == item["updated_sha256"]:
            replace_exact(target, backup, current)
    receipt["state"] = "restored"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "restored_streams": len(receipt["streams"])}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    commands.add_parser("stage")
    rollback = commands.add_parser("restore")
    rollback.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        print(json.dumps(preflight(), indent=2))
    elif args.command == "stage":
        stage()
    else:
        restore(args.run)
