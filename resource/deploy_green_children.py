"""Reversible two-stream test of green shaderless persistent-fire children."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import GAME, ROOT, RUNS, game_closed, nonredirected, receipt_write, replace_exact, save_new, sha


GREEN = ROOT / "analysis/liquid-green-children-24735202"
BLUE = ROOT / "analysis/liquid-blue-defaults-24735202"
V2 = ROOT / "analysis/liquid-bundle-v2-trial-24735202"
BUNDLE_SHA = "6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d"
LUA_SHA = "3bb1fc0e64f2ab12439a73bba3a916f75d4c823140a7cc58c2fabdf10411efbd"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def preflight():
    report = json.loads((GREEN / "report.json").read_text())
    blue = json.loads((BLUE / "report.json").read_text())
    require(report["hue"] == 120 and len(report["changes"]) == 2
            and blue["bundle_sha256"] == BUNDLE_SHA
            and sha((GAME / "bundle/b224998193576995").read_bytes()) == BUNDLE_SHA,
            "Incorrect green test or liquid bundle")
    require(sha((GAME / "mods/RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua").read_bytes()) == LUA_SHA,
            "Diagnostic Lua changed")
    blue_items = {row["stream"]: row for row in blue["changed"]}
    streams = []
    for row in blue["changed"]:
        relative = row["stream"]
        if row["shader_default_changed"]:
            require(sha((GAME / relative).read_bytes()) == row["v2_sha256"]
                    and sha((V2 / relative).read_bytes()) == row["v2_sha256"],
                    "Parent shader material changed: " + relative)
    for item in report["changes"]:
        relative = item["stream"]
        target = GAME / relative
        nonredirected(target)
        require(not blue_items[relative]["shader_default_changed"]
                and blue_items[relative]["blue_sha256"] == item["blue_sha256"]
                and sha(target.read_bytes()) == item["blue_sha256"]
                and sha((GREEN / relative).read_bytes()) == item["green_sha256"]
                and target.stat().st_size == item["bytes"],
                "Installed blue child or green candidate changed: " + relative)
        streams.append({"relative": relative, "previous_sha256": item["blue_sha256"],
                        "updated_sha256": item["green_sha256"], "bytes": item["bytes"]})
    require(len(streams) == 2, "Exactly two child streams required")
    order = GAME / "mods/mod_load_order.txt"
    nonredirected(order)
    raw = order.read_bytes()
    require(sum(line.strip(b"\r\n") == b"RainbowBarrels" for line in raw.splitlines()) == 1,
            "Vortex load order no longer includes exactly one RainbowBarrels")
    return {"game_root": str(GAME), "streams": streams, "bundle_sha256": BUNDLE_SHA,
            "lua_sha256": LUA_SHA, "vortex_load_order_sha256": sha(raw),
            "scope": "read-only two-child preflight; v2 shader parents, bundle, Lua and Vortex list unchanged"}


def stage():
    game_closed()
    plan = preflight()
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + "-green-children")
    run.mkdir()
    for item in plan["streams"]:
        save_new(run / Path(item["relative"]).name, (GAME / item["relative"]).read_bytes())
    receipt = {"kind": "green-children", "game_root": str(GAME), "state": "prepared",
               "streams": plan["streams"], "bundle_sha256": BUNDLE_SHA, "lua_sha256": LUA_SHA,
               "vortex_load_order_sha256_at_stage": plan["vortex_load_order_sha256"],
               "rollback": "Close Darktide; restore only two exact blue child streams with deploy_green_children.py restore --run <this directory>. Parent streams, bundle, Lua and Vortex files are not owned by this test."}
    receipt_write(run, receipt)
    for item in receipt["streams"]:
        replace_exact(GAME / item["relative"], (GREEN / item["relative"]).read_bytes(), item["previous_sha256"])
    receipt["state"] = "green_children_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "updated_children": len(receipt["streams"]),
                      "parents_bundle_lua_vortex_unchanged": True}, indent=2))


def restore(run):
    game_closed()
    run = run.resolve()
    require(run.parent == RUNS.resolve() and (run / "receipt.json").is_file(), "Unknown green-children run")
    receipt = json.loads((run / "receipt.json").read_text())
    require(receipt["kind"] == "green-children" and receipt["game_root"] == str(GAME),
            "Wrong green-children receipt")
    for item in receipt["streams"]:
        target = GAME / item["relative"]
        old = (run / Path(item["relative"]).name).read_bytes()
        require(sha(old) == item["previous_sha256"], "Previous blue child backup changed")
        current = sha(target.read_bytes())
        require(current in (item["previous_sha256"], item["updated_sha256"]),
                "Child stream changed outside this test")
        if current == item["updated_sha256"]:
            replace_exact(target, old, current)
    receipt["state"] = "restored"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "restored_children": len(receipt["streams"])}, indent=2))


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
