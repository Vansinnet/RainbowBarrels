"""Reversible one-bundle test of hue-authored persistent-fire type-2 RGB curves."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import GAME, ROOT, RUNS, game_closed, nonredirected, receipt_write, replace_exact, save_new, sha


TRIAL = ROOT / "analysis/liquid-floor-graph-trial-24735202"
WHEEL = ROOT / "analysis/liquid-hue-wheel-24735202"
WHEEL_RUN = ROOT / "analysis/deployment-runs/20260923T172524Z-2c23ccf6-ground-wheel"
PACKAGE = "bundle/b224998193576995"
LUA = "mods/RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua"
BASE_SHA = "ba72ce819fa19d2c7c9ba3449e58013c2a3b1247f109d082da32682a2b0aae31"
CANDIDATE_SHA = "7181ef9b900ad89bd5d43759c28f027fc3dbf9b2de68d0ff7beaa798c1900820"
LUA_SHA = "eda5aab1101ac5980b81a7e077c3f56f9f1f7e56f25e9d0ef9dd4a642b5e9991"
EXPLOSION_SHA = "a0a15fcde68bbd2d7a4ec0cd998bd7d143d2999d3d0b8a74baa60340b529cff9"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def preflight():
    report = json.loads((TRIAL / "report.json").read_text())
    prior = json.loads((WHEEL_RUN / "receipt.json").read_text())
    require(report["build"] == "24735202" and report["base_bundle_sha256"] == BASE_SHA
            and report["candidate_bundle_sha256"] == CANDIDATE_SHA
            and report["filled_particles_recolored"] == 360
            and report["rim_particles_unchanged"] == 360
            and report["material_streams_unchanged"] == 1080,
            "Candidate color-graph profile changed")
    require(prior["kind"] == "ground-wheel" and prior["state"] == "ground_wheel_installed"
            and prior["updated_bundle_sha256"] == BASE_SHA and len(prior["new_streams"]) == 1080,
            "Current hue-wheel owned installation changed")
    for path in (GAME, GAME / "bundle", GAME / "bundle/data/rb", GAME / "mods",
                 GAME / "mods/RainbowBarrels", GAME / PACKAGE, GAME / LUA):
        nonredirected(path)
    require(sha((GAME / PACKAGE).read_bytes()) == BASE_SHA
            and sha((WHEEL / PACKAGE).read_bytes()) == BASE_SHA
            and sha((TRIAL / PACKAGE).read_bytes()) == CANDIDATE_SHA,
            "Installed/source/candidate bundle identity")
    require(sha((GAME / LUA).read_bytes()) == LUA_SHA
            and sha((GAME / "bundle/98bb14b1d247a0c8").read_bytes()) == EXPLOSION_SHA,
            "Runtime Lua or explosion bundle changed")
    for row in prior["new_streams"]:
        target = GAME / row["relative"]
        nonredirected(target)
        require(sha(target.read_bytes()) == row["sha256"],
                "Previously installed owned material stream changed: " + row["relative"])
    order = GAME / "mods/mod_load_order.txt"
    nonredirected(order)
    raw = order.read_bytes()
    require(sum(line.strip(b"\r\n") == b"RainbowBarrels" for line in raw.splitlines()) == 1,
            "Vortex load order no longer includes exactly one RainbowBarrels")
    return {"game_root": str(GAME), "previous_bundle_sha256": BASE_SHA,
            "updated_bundle_sha256": CANDIDATE_SHA, "lua_sha256": LUA_SHA,
            "prior_owned_streams_verified": len(prior["new_streams"]),
            "vortex_load_order_sha256": sha(raw),
            "scope": "read-only one-bundle preflight; Lua, all 1080 streams, explosion and Vortex unchanged"}


def stage():
    game_closed()
    plan = preflight()
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + "-floor-graph")
    run.mkdir()
    save_new(run / "previous.bundle", (GAME / PACKAGE).read_bytes())
    receipt = {"kind": "floor-graph", "game_root": str(GAME), "state": "prepared",
               "resource": PACKAGE, "previous_bundle_sha256": BASE_SHA,
               "updated_bundle_sha256": CANDIDATE_SHA,
               "lua_sha256": LUA_SHA,
               "prior_owned_streams_verified": plan["prior_owned_streams_verified"],
               "vortex_load_order_sha256_at_stage": plan["vortex_load_order_sha256"],
               "rollback": "Close Darktide, then run deploy_liquid_floor_graphs.py restore --run <this directory>. Restore only the exact previous b224 bundle; leave every stream, Lua, explosion and Vortex file untouched."}
    receipt_write(run, receipt)
    replace_exact(GAME / PACKAGE, (TRIAL / PACKAGE).read_bytes(), BASE_SHA)
    receipt["state"] = "floor_graph_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "installed_bundle_sha256": sha((GAME / PACKAGE).read_bytes()),
                      "streams_lua_explosion_vortex_unchanged": True}, indent=2))


def restore(run):
    game_closed()
    run = run.resolve()
    require(run.parent == RUNS.resolve() and (run / "receipt.json").is_file(), "Unknown floor-graph run")
    receipt = json.loads((run / "receipt.json").read_text())
    require(receipt["kind"] == "floor-graph" and receipt["game_root"] == str(GAME)
            and receipt["resource"] == PACKAGE, "Wrong floor-graph receipt")
    old = (run / "previous.bundle").read_bytes()
    require(sha(old) == receipt["previous_bundle_sha256"], "Previous hue-wheel backup changed")
    current = sha((GAME / PACKAGE).read_bytes())
    require(current in (receipt["previous_bundle_sha256"], receipt["updated_bundle_sha256"]),
            "Installed liquid bundle changed outside this test")
    if current == receipt["updated_bundle_sha256"]:
        replace_exact(GAME / PACKAGE, old, current)
    receipt["state"] = "restored"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "restored_bundle_sha256": sha((GAME / PACKAGE).read_bytes())}, indent=2))


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
