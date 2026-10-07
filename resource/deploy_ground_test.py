"""Staged, hash-pinned test of prop-fire resource variants; not a release installer."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import (GAME, RUNS, ROOT, game_closed, nonredirected,
                         receipt_write, replace_exact, save_new, sha)
from prepare_ground_deployment import (GAME_BUNDLE, LIQUID, OUT as PREFLIGHT,
                                       STOCK, PREVIOUS_EXPLOSION)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def owned_run(path, kind):
    path = path.resolve()
    require(path.parent == RUNS.resolve() and (path / "receipt.json").is_file(), "Unknown RainbowBarrels test receipt")
    receipt = json.loads((path / "receipt.json").read_text())
    require(receipt["kind"] == kind and receipt["game_root"] == str(GAME), "Wrong game/test receipt")
    return path, receipt


def check_plan():
    report = json.loads((PREFLIGHT / "preflight.json").read_text())
    require(report["game_root"] == str(GAME) and report["steam_build"] == "24735202",
            "Unsupported game root/build")
    require(report["stock_sha256"] == STOCK and report["previous_explosion_sha256"] == PREVIOUS_EXPLOSION,
            "Wrong source package identities")
    require(sha((LIQUID / "bundle/b224998193576995").read_bytes()) == report["candidate_sha256"],
            "Edited liquid package drift")
    require(sha((PREFLIGHT / "b224998193576995.noop.bundle").read_bytes()) == report["noop_sha256"],
            "Physical no-op package drift")
    for parent in (GAME, GAME / "bundle", GAME / "bundle/data", GAME / "bundle/data/rb",
                   GAME / "mods", GAME / "mods/RainbowBarrels"):
        nonredirected(parent)
        require(parent.is_dir(), "Required installed game directory missing: " + str(parent))
    order = GAME / "mods/mod_load_order.txt"
    nonredirected(order)
    require(sha(order.read_bytes()) == report["load_order_sha256"],
            "Vortex-managed mod order changed since the read-only preflight")
    require(sha((GAME / "bundle/98bb14b1d247a0c8").read_bytes()) == PREVIOUS_EXPLOSION,
            "Previously tested explosion package changed")
    nonredirected(GAME_BUNDLE)
    require(GAME_BUNDLE.is_file() and sha(GAME_BUNDLE.read_bytes()) == STOCK,
            "Existing liquid package must be the original stock version")
    for item in report["new_streams"]:
        target = GAME / item["relative"]
        nonredirected(target)
        require(not target.exists(), "New liquid stream path is already occupied")
        payload = (LIQUID / item["relative"]).read_bytes()
        require(sha(payload) == item["sha256"] and len(payload) == item["bytes"],
                "Offline authored stream drift")
    for item in report["changed_mod_files"]:
        target = GAME / item["relative"]
        nonredirected(target)
        require(sha(target.read_bytes()) == item["deployed_sha256"],
                "Already deployed mod file was changed independently")
        relative = item["relative"].removeprefix("mods/RainbowBarrels/")
        updated = (ROOT / relative).read_bytes()
        require(sha(updated) == item["new_sha256"] and len(updated) == item["new_bytes"],
                "Changed Lua source no longer matches approved preflight")
    return report


def make_run(name):
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + "-" + name)
    run.mkdir()
    return run


def stage_noop():
    game_closed()
    plan = check_plan()
    run = make_run("ground-noop")
    original = GAME_BUNDLE.read_bytes()
    save_new(run / "original.bundle", original)
    receipt = {"kind": "ground-noop", "game_root": str(GAME), "state": "prepared",
               "stock_sha256": STOCK, "backup_sha256": sha(original),
               "installed_sha256": plan["noop_sha256"], "resource": "bundle/b224998193576995"}
    receipt_write(run, receipt)
    replace_exact(GAME_BUNDLE, (PREFLIGHT / "b224998193576995.noop.bundle").read_bytes(), STOCK)
    receipt["state"] = "noop_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "installed_sha256": receipt["installed_sha256"],
                      "rollback": f'python -B "mods/active/RainbowBarrels/resource/deploy_ground_test.py" restore-noop --run "{run}"'}, indent=2))


def restore_noop(run):
    game_closed()
    run, receipt = owned_run(run, "ground-noop")
    stock = (run / "original.bundle").read_bytes()
    require(sha(stock) == STOCK == receipt["backup_sha256"], "Stock rollback material changed")
    current = sha(GAME_BUNDLE.read_bytes())
    if current == receipt["installed_sha256"]:
        replace_exact(GAME_BUNDLE, stock, current)
    else:
        require(current == STOCK, "Game bundle changed unexpectedly; refusing rollback")
    receipt["state"] = "restored"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "stock_sha256": sha(GAME_BUNDLE.read_bytes())}, indent=2))


def stage_candidate(noop_run):
    game_closed()
    noop, first = owned_run(noop_run, "ground-noop")
    observation = json.loads((noop / "observation.json").read_text())
    require(first["state"] == "restored" and observation["stage"] == "ground-noop-game-acceptance"
            and observation["installed_bundle_sha256"] == first["installed_sha256"],
            "Ground-fire no-op gameplay result is missing")
    plan = check_plan()
    run = make_run("ground-candidate")
    save_new(run / "original.bundle", GAME_BUNDLE.read_bytes())
    for item in plan["changed_mod_files"]:
        source = GAME / item["relative"]
        save_new(run / Path(item["relative"]).name, source.read_bytes())
    receipt = {"kind": "ground-candidate", "game_root": str(GAME), "state": "prepared",
               "no_op_run": str(noop), "resource": "bundle/b224998193576995",
               "stock_sha256": STOCK, "installed_sha256": plan["candidate_sha256"],
               "load_order_sha256_at_stage": plan["load_order_sha256"],
               "new_streams": plan["new_streams"], "changed_mod_files": plan["changed_mod_files"],
               "rollback": "Close Darktide; restore the SHA-pinned original b224 bundle and two prior deployed Lua files. Remove only the five owned liquid streams. Do not overwrite Vortex's load order."}
    receipt_write(run, receipt)
    for item in receipt["new_streams"]:
        save_new(GAME / item["relative"], (LIQUID / item["relative"]).read_bytes())
    for item in receipt["changed_mod_files"]:
        relative = item["relative"].removeprefix("mods/RainbowBarrels/")
        replace_exact(GAME / item["relative"], (ROOT / relative).read_bytes(), item["deployed_sha256"])
    replace_exact(GAME_BUNDLE, (LIQUID / "bundle/b224998193576995").read_bytes(), STOCK)
    receipt["state"] = "candidate_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "installed_sha256": receipt["installed_sha256"],
                      "rollback": f'python -B "mods/active/RainbowBarrels/resource/deploy_ground_test.py" restore-candidate --run "{run}"'}, indent=2))


def restore_candidate(run):
    game_closed()
    run, receipt = owned_run(run, "ground-candidate")
    backup = (run / "original.bundle").read_bytes()
    require(sha(backup) == STOCK == receipt["stock_sha256"], "Original liquid bundle backup changed")
    current = sha(GAME_BUNDLE.read_bytes())
    require(current in (STOCK, receipt["installed_sha256"]), "Liquid bundle changed outside the test")
    for item in receipt["new_streams"]:
        dest = GAME / item["relative"]
        nonredirected(dest)
        if dest.exists():
            require(sha(dest.read_bytes()) == item["sha256"], "Changed owned liquid stream")
    for item in receipt["changed_mod_files"]:
        dest = GAME / item["relative"]
        nonredirected(dest)
        require(sha((run / dest.name).read_bytes()) == item["deployed_sha256"],
                "Previous deployed Lua backup changed")
        require(sha(dest.read_bytes()) in (item["deployed_sha256"], item["new_sha256"]),
                "Deployed Lua changed outside this test")
    if current == receipt["installed_sha256"]:
        replace_exact(GAME_BUNDLE, backup, current)
    for item in receipt["changed_mod_files"]:
        dest = GAME / item["relative"]
        if sha(dest.read_bytes()) == item["new_sha256"]:
            replace_exact(dest, (run / dest.name).read_bytes(), item["new_sha256"])
    for item in receipt["new_streams"]:
        dest = GAME / item["relative"]
        if dest.exists():
            dest.unlink()
    receipt["state"] = "restored"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "stock_sha256": sha(GAME_BUNDLE.read_bytes()),
                      "load_order_left_unchanged": True}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    commands.add_parser("stage-noop")
    recover = commands.add_parser("restore-noop")
    recover.add_argument("--run", type=Path, required=True)
    candidate = commands.add_parser("stage-candidate")
    candidate.add_argument("--noop-run", type=Path, required=True)
    recover_candidate = commands.add_parser("restore-candidate")
    recover_candidate.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        plan = check_plan()
        print(json.dumps({"status": "read-only preflight ready", "stock_sha256": STOCK,
                          "extra_streams": len(plan["new_streams"]),
                          "updated_lua_files": len(plan["changed_mod_files"])}, indent=2))
    elif args.command == "stage-noop":
        stage_noop()
    elif args.command == "restore-noop":
        restore_noop(args.run)
    elif args.command == "stage-candidate":
        stage_candidate(args.noop_run)
    else:
        restore_candidate(args.run)
