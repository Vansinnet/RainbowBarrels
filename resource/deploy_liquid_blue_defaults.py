"""Reversible fixed-blue diagnostic for five owned liquid material streams."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import GAME, ROOT, RUNS, game_closed, nonredirected, receipt_write, replace_exact, save_new, sha


BASE = ROOT / "analysis/liquid-bundle-v2-trial-24735202"
BLUE = ROOT / "analysis/liquid-blue-defaults-24735202"
BUNDLE = "6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d"
LUA = "3bb1fc0e64f2ab12439a73bba3a916f75d4c823140a7cc58c2fabdf10411efbd"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def preflight():
    base = json.loads((BASE / "report.json").read_text())
    report = json.loads((BLUE / "report.json").read_text())
    require(base["candidate_bundle_sha256"] == report["bundle_sha256"] == BUNDLE
            and sha((GAME / "bundle/b224998193576995").read_bytes()) == BUNDLE,
            "Installed liquid bundle changed")
    require(sha((GAME / "mods/RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua").read_bytes()) == LUA,
            "Installed diagnostic Lua changed")
    assets = {item["stream"]: item for item in base["added_assets"] if item["kind"] == "material"}
    streams = []
    for row in report["changed"]:
        relative = row["stream"]
        target = GAME / relative
        new = BLUE / relative
        nonredirected(target)
        require(assets[relative]["sha256"] == row["v2_sha256"]
                and sha(target.read_bytes()) == row["v2_sha256"]
                and sha(new.read_bytes()) == row["blue_sha256"]
                and target.stat().st_size == row["bytes"] == new.stat().st_size,
                "Material stream changed from pinned v2: " + relative)
        streams.append({"relative": relative, "previous_sha256": row["v2_sha256"],
                        "updated_sha256": row["blue_sha256"], "bytes": row["bytes"]})
    require(len(streams) == 5 and sum(row["shader_default_changed"] for row in report["changed"]) == 3,
            "Expected exactly three shader parents and two children")
    order = GAME / "mods/mod_load_order.txt"
    nonredirected(order)
    raw = order.read_bytes()
    require(sum(line.strip(b"\r\n") == b"RainbowBarrels" for line in raw.splitlines()) == 1,
            "Vortex load order no longer includes exactly one RainbowBarrels")
    return {"game_root": str(GAME), "streams": streams, "bundle_sha256": BUNDLE,
            "lua_sha256": LUA, "vortex_load_order_sha256": sha(raw),
            "scope": "read-only five-stream fixed-blue preflight; bundle, Lua and Vortex list unchanged"}


def stage():
    game_closed()
    plan = preflight()
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + "-blue-defaults")
    run.mkdir()
    for item in plan["streams"]:
        save_new(run / Path(item["relative"]).name, (GAME / item["relative"]).read_bytes())
    receipt = {"kind": "blue-defaults", "game_root": str(GAME), "state": "prepared",
               "streams": plan["streams"], "bundle_sha256": BUNDLE, "lua_sha256": LUA,
               "vortex_load_order_sha256_at_stage": plan["vortex_load_order_sha256"],
               "rollback": "Close Darktide and restore only the five exact previous material streams with deploy_liquid_blue_defaults.py restore --run <this directory>. Bundle, Lua and Vortex files are not owned by this diagnostic."}
    receipt_write(run, receipt)
    for item in receipt["streams"]:
        replace_exact(GAME / item["relative"], (BLUE / item["relative"]).read_bytes(), item["previous_sha256"])
    receipt["state"] = "blue_defaults_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "updated_streams": len(receipt["streams"]),
                      "bundle_lua_and_vortex_unchanged": True}, indent=2))


def restore(run):
    game_closed()
    run = run.resolve()
    require(run.parent == RUNS.resolve() and (run / "receipt.json").is_file(), "Unknown blue-defaults run")
    receipt = json.loads((run / "receipt.json").read_text())
    require(receipt["kind"] == "blue-defaults" and receipt["game_root"] == str(GAME),
            "Wrong blue-defaults receipt")
    for item in receipt["streams"]:
        target = GAME / item["relative"]
        old = (run / Path(item["relative"]).name).read_bytes()
        require(sha(old) == item["previous_sha256"], "Prior material backup changed")
        current = sha(target.read_bytes())
        require(current in (item["previous_sha256"], item["updated_sha256"]),
                "Material stream changed outside this diagnostic")
        if current == item["updated_sha256"]:
            replace_exact(target, old, current)
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
