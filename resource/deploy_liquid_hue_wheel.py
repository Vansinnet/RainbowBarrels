"""Hash-pinned, reversible test of the complete 360-degree ground-fire wheel."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import GAME, ROOT, RUNS, game_closed, nonredirected, receipt_write, replace_exact, save_new, sha


WHEEL = ROOT / "analysis/liquid-hue-wheel-24735202"
BASE = ROOT / "analysis/liquid-bundle-v2-trial-24735202"
GREEN = ROOT / "analysis/liquid-green-children-24735202"
CHILD_RUN = ROOT / "analysis/deployment-runs/20260923T162039Z-fa106e3b-child-only"
GREEN_RUN = ROOT / "analysis/deployment-runs/20260923T170223Z-1991a1a1-green-children"
PACKAGE = "bundle/b224998193576995"
LUA = "mods/RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua"
BASE_BUNDLE_SHA = "6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d"
BASE_LUA_SHA = "3bb1fc0e64f2ab12439a73bba3a916f75d4c823140a7cc58c2fabdf10411efbd"
EXPLOSION_SHA = "a0a15fcde68bbd2d7a4ec0cd998bd7d143d2999d3d0b8a74baa60340b529cff9"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def preflight():
    report = json.loads((WHEEL / "report.json").read_text())
    source = ROOT / "scripts/mods/RainbowBarrels/RainbowBarrels.lua"
    require(report["build"] == "24735202" and report["base_bundle_sha256"] == BASE_BUNDLE_SHA
            and report["candidate_resources"] == 1910 and report["base_resources"] == 110
            and len(report["added_material_streams"]) == 1080
            and len(report["generated_particles"]) == 720,
            "Ground hue wheel inventory or game build changed")
    require(sha((GAME / PACKAGE).read_bytes()) == BASE_BUNDLE_SHA
            and sha((WHEEL / PACKAGE).read_bytes()) == report["candidate_bundle_sha256"]
            and sha((GAME / "bundle/98bb14b1d247a0c8").read_bytes()) == EXPLOSION_SHA,
            "Pinned ground/explosion bundle changed")
    require(sha((GAME / LUA).read_bytes()) == BASE_LUA_SHA and sha(source.read_bytes()) != BASE_LUA_SHA,
            "Installed Lua or new runtime source changed")
    for run, kind, status in ((CHILD_RUN, "child-only", "child_only_installed"),
                               (GREEN_RUN, "green-children", "green_children_installed")):
        receipt = json.loads((run / "receipt.json").read_text())
        require(receipt["kind"] == kind and receipt["state"] == status,
                "Earlier isolated material trial no longer forms the baseline")
    materials = {row["stream"]: row for row in json.loads((BASE / "report.json").read_text())["added_assets"]
                 if row["kind"] == "material"}
    green = {row["stream"]: row for row in json.loads((GREEN / "report.json").read_text())["changes"]}
    for relative, row in materials.items():
        target = GAME / relative
        nonredirected(target)
        expected = green[relative]["green_sha256"] if relative in green else row["sha256"]
        require(sha(target.read_bytes()) == expected,
                "Previously installed child or shader parent changed: " + relative)
    for parent in (GAME, GAME / "bundle", GAME / "bundle/data", GAME / "bundle/data/rb",
                   GAME / "mods", GAME / "mods/RainbowBarrels"):
        nonredirected(parent)
        require(parent.is_dir(), "Required installed directory is missing")
    nonredirected(GAME / PACKAGE)
    nonredirected(GAME / LUA)
    names = set()
    streams = []
    for row in report["added_material_streams"]:
        relative = row["stream"]
        require(relative.startswith("bundle/data/rb/") and relative not in names,
                "Invalid or repeated owned stream")
        names.add(relative)
        target = GAME / relative
        nonredirected(target)
        require(not target.exists(), "New material stream path is already occupied: " + relative)
        payload = (WHEEL / relative).read_bytes()
        require(sha(payload) == row["sha256"] and len(payload) == row["bytes"],
                "Authored wheel stream changed: " + relative)
        streams.append({"relative": relative, "sha256": row["sha256"], "bytes": row["bytes"]})
    require(len(streams) == 1080, "Incomplete new stream list")
    order = GAME / "mods/mod_load_order.txt"
    nonredirected(order)
    raw = order.read_bytes()
    require(sum(line.strip(b"\r\n") == b"RainbowBarrels" for line in raw.splitlines()) == 1,
            "Vortex load order no longer includes exactly one RainbowBarrels")
    return {"game_root": str(GAME), "new_streams": streams,
            "previous_bundle_sha256": BASE_BUNDLE_SHA, "updated_bundle_sha256": report["candidate_bundle_sha256"],
            "previous_lua_sha256": BASE_LUA_SHA, "updated_lua_sha256": sha(source.read_bytes()),
            "vortex_load_order_sha256": sha(raw),
            "scope": "read-only 1080-new-stream + one-bundle + one-Lua preflight; prior resources and Vortex list preserved"}


def stage():
    game_closed()
    plan = preflight()
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + "-ground-wheel")
    run.mkdir()
    save_new(run / "previous.bundle", (GAME / PACKAGE).read_bytes())
    save_new(run / "previous.lua", (GAME / LUA).read_bytes())
    receipt = {"kind": "ground-wheel", "game_root": str(GAME), "state": "prepared",
               "package": PACKAGE, "lua": LUA, "new_streams": plan["new_streams"],
               "previous_bundle_sha256": plan["previous_bundle_sha256"],
               "updated_bundle_sha256": plan["updated_bundle_sha256"],
               "previous_lua_sha256": plan["previous_lua_sha256"],
               "updated_lua_sha256": plan["updated_lua_sha256"],
               "vortex_load_order_sha256_at_stage": plan["vortex_load_order_sha256"],
               "rollback": "Close Darktide; use deploy_liquid_hue_wheel.py restore --run <this directory> to restore only the exact prior b224 bundle and Lua file and remove only 1080 exact owned streams. Leave explosion files, five existing liquid streams and Vortex load order untouched."}
    receipt_write(run, receipt)
    for row in receipt["new_streams"]:
        save_new(GAME / row["relative"], (WHEEL / row["relative"]).read_bytes())
    replace_exact(GAME / PACKAGE, (WHEEL / PACKAGE).read_bytes(), receipt["previous_bundle_sha256"])
    replace_exact(GAME / LUA, (ROOT / "scripts/mods/RainbowBarrels/RainbowBarrels.lua").read_bytes(),
                  receipt["previous_lua_sha256"])
    receipt["state"] = "ground_wheel_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "new_streams": len(receipt["new_streams"]),
                      "bundle_sha256": sha((GAME / PACKAGE).read_bytes()),
                      "lua_sha256": sha((GAME / LUA).read_bytes()),
                      "existing_streams_explosion_and_vortex_unchanged": True}, indent=2))


def restore(run):
    game_closed()
    run = run.resolve()
    require(run.parent == RUNS.resolve() and (run / "receipt.json").is_file(), "Unknown ground-wheel run")
    receipt = json.loads((run / "receipt.json").read_text())
    require(receipt["kind"] == "ground-wheel" and receipt["game_root"] == str(GAME)
            and receipt["package"] == PACKAGE and receipt["lua"] == LUA,
            "Wrong ground-wheel receipt")
    old_bundle = (run / "previous.bundle").read_bytes()
    old_lua = (run / "previous.lua").read_bytes()
    require(sha(old_bundle) == receipt["previous_bundle_sha256"]
            and sha(old_lua) == receipt["previous_lua_sha256"],
            "Rollback backup changed")
    for relative, previous, updated in ((PACKAGE, receipt["previous_bundle_sha256"],
                                        receipt["updated_bundle_sha256"]),
                                        (LUA, receipt["previous_lua_sha256"],
                                         receipt["updated_lua_sha256"])):
        require(sha((GAME / relative).read_bytes()) in (previous, updated),
                "Installed owned file changed outside this test: " + relative)
    for row in receipt["new_streams"]:
        target = GAME / row["relative"]
        nonredirected(target)
        if target.exists():
            require(sha(target.read_bytes()) == row["sha256"],
                    "New owned stream changed outside this test: " + row["relative"])
    if sha((GAME / PACKAGE).read_bytes()) == receipt["updated_bundle_sha256"]:
        replace_exact(GAME / PACKAGE, old_bundle, receipt["updated_bundle_sha256"])
    if sha((GAME / LUA).read_bytes()) == receipt["updated_lua_sha256"]:
        replace_exact(GAME / LUA, old_lua, receipt["updated_lua_sha256"])
    for row in receipt["new_streams"]:
        target = GAME / row["relative"]
        if target.exists():
            target.unlink()
    receipt["state"] = "restored"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "bundle_sha256": sha((GAME / PACKAGE).read_bytes()),
                      "lua_sha256": sha((GAME / LUA).read_bytes()),
                      "vortex_load_order_untouched": True}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    commands.add_parser("stage")
    rollback = commands.add_parser("restore")
    rollback.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        result = preflight()
        print(json.dumps({key: result[key] for key in ("game_root", "previous_bundle_sha256",
                                                     "updated_bundle_sha256", "previous_lua_sha256",
                                                     "updated_lua_sha256", "vortex_load_order_sha256", "scope")}
                         | {"new_streams": len(result["new_streams"])}, indent=2))
    elif args.command == "stage":
        stage()
    else:
        restore(args.run)
