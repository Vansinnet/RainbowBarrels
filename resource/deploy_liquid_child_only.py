"""Reversible three-stream test: keep blue child defaults and restore v2 shader parents."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import GAME, ROOT, RUNS, game_closed, nonredirected, receipt_write, replace_exact, save_new, sha


V2 = ROOT / "analysis/liquid-bundle-v2-trial-24735202"
BLUE = ROOT / "analysis/liquid-blue-defaults-24735202"
BUNDLE_SHA = "6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d"
LUA_SHA = "3bb1fc0e64f2ab12439a73bba3a916f75d4c823140a7cc58c2fabdf10411efbd"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def preflight():
    blue = json.loads((BLUE / "report.json").read_text())
    v2 = json.loads((V2 / "report.json").read_text())
    require(blue["bundle_sha256"] == v2["candidate_bundle_sha256"] == BUNDLE_SHA
            and sha((GAME / "bundle/b224998193576995").read_bytes()) == BUNDLE_SHA,
            "Liquid bundle changed")
    require(sha((GAME / "mods/RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua").read_bytes()) == LUA_SHA,
            "Installed Lua probe changed")
    materials = {row["stream"]: row for row in v2["added_assets"] if row["kind"] == "material"}
    parents = []
    for row in blue["changed"]:
        relative = row["stream"]
        target = GAME / relative
        nonredirected(target)
        require(materials[relative]["sha256"] == row["v2_sha256"]
                and sha((V2 / relative).read_bytes()) == row["v2_sha256"]
                and sha((BLUE / relative).read_bytes()) == row["blue_sha256"]
                and sha(target.read_bytes()) == row["blue_sha256"],
                "Installed blue material or v2 source changed: " + relative)
        if row["shader_default_changed"]:
            parents.append({"relative": relative, "previous_sha256": row["blue_sha256"],
                            "updated_sha256": row["v2_sha256"], "bytes": row["bytes"]})
    require(len(parents) == 3 and len(blue["changed"]) == 5,
            "Exactly three parents and two unchanged blue children required")
    order = GAME / "mods/mod_load_order.txt"
    nonredirected(order)
    raw = order.read_bytes()
    require(sum(line.strip(b"\r\n") == b"RainbowBarrels" for line in raw.splitlines()) == 1,
            "Vortex load order no longer includes exactly one RainbowBarrels")
    return {"game_root": str(GAME), "streams": parents, "bundle_sha256": BUNDLE_SHA,
            "lua_sha256": LUA_SHA, "vortex_load_order_sha256": sha(raw),
            "scope": "read-only three-parent preflight; two blue children, bundle, Lua and Vortex list unchanged"}


def stage():
    game_closed()
    plan = preflight()
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + "-child-only")
    run.mkdir()
    for item in plan["streams"]:
        save_new(run / Path(item["relative"]).name, (GAME / item["relative"]).read_bytes())
    receipt = {"kind": "child-only", "game_root": str(GAME), "state": "prepared",
               "streams": plan["streams"], "bundle_sha256": BUNDLE_SHA, "lua_sha256": LUA_SHA,
               "vortex_load_order_sha256_at_stage": plan["vortex_load_order_sha256"],
               "rollback": "Close Darktide; restore only the three exact blue parent streams using deploy_liquid_child_only.py restore --run <this directory>. Two blue children, bundle, Lua and Vortex files are not owned by this test."}
    receipt_write(run, receipt)
    for item in receipt["streams"]:
        replace_exact(GAME / item["relative"], (V2 / item["relative"]).read_bytes(), item["previous_sha256"])
    receipt["state"] = "child_only_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "v2_parents_restored": len(receipt["streams"]),
                      "blue_children_bundle_lua_vortex_unchanged": True}, indent=2))


def restore(run):
    game_closed()
    run = run.resolve()
    require(run.parent == RUNS.resolve() and (run / "receipt.json").is_file(), "Unknown child-only run")
    receipt = json.loads((run / "receipt.json").read_text())
    require(receipt["kind"] == "child-only" and receipt["game_root"] == str(GAME),
            "Wrong child-only receipt")
    for item in receipt["streams"]:
        target = GAME / item["relative"]
        old = (run / Path(item["relative"]).name).read_bytes()
        require(sha(old) == item["previous_sha256"], "Previous blue parent backup changed")
        current = sha(target.read_bytes())
        require(current in (item["previous_sha256"], item["updated_sha256"]),
                "Parent material changed outside this test")
        if current == item["updated_sha256"]:
            replace_exact(target, old, current)
    receipt["state"] = "restored"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "restored_parents": len(receipt["streams"])}, indent=2))


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
