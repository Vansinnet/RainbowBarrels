"""Reversible, hash-pinned local RainbowBarrels game test; not a release installer."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import (GAME, GAME_BUNDLE, RUNS, RECEIPT, STOCK, CANDIDATE, ROOT,
                         game_closed, nonredirected, preflight, receipt_write,
                         replace_exact, save_new, sha)


MOD = GAME / "mods/RainbowBarrels"
STREAMS = GAME / "bundle/data/rb"
ORDER = GAME / "mods/mod_load_order.txt"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def noop_confirmed(run):
    path = run.resolve()
    require(path.parent == RUNS.resolve(), "No-op run must be owned by RainbowBarrels")
    receipt = json.loads((path / RECEIPT).read_text())
    observation = json.loads((path / "observation.json").read_text())
    require(receipt["kind"] == "noop" and receipt["state"] == "restored"
            and receipt["stock_sha256"] == STOCK
            and observation["installed_bundle_sha256"] == receipt["installed_sha256"]
            and observation["stage"] == "stored-noop-game-acceptance",
            "No-op test is not confirmed and restored")
    return path


def baseline(plan):
    game_closed()
    stock = GAME_BUNDLE.read_bytes()
    original_order = ORDER.read_bytes()
    require(sha(stock) == STOCK and sha(original_order) == plan["load_order_sha256"],
            "Game bundle or Vortex load order changed")
    require(sha((CANDIDATE / "bundle/98bb14b1d247a0c8").read_bytes())
            == plan["candidate_bundle_sha256"], "Candidate bundle identity changed")
    addition = b"RainbowBarrels\r\n"
    updated_order = original_order + (b"" if original_order.endswith((b"\n", b"\r")) else b"\r\n") + addition
    require(updated_order != original_order, "No new load-order line")
    return stock, original_order, updated_order


def verify_owned_files(receipt):
    for entry in receipt["resources"] + receipt["mod_files"]:
        path = GAME / entry["relative"]
        nonredirected(path)
        if path.exists():
            require(path.is_file() and sha(path.read_bytes()) == entry["sha256"],
                    "Changed owned file, refusing rollback: " + str(path))
    for folder, files in ((STREAMS, receipt["resources"]), (MOD, receipt["mod_files"])):
        nonredirected(folder)
        if folder.exists():
            require(folder.is_dir(), "Changed owned directory")
            known = {entry["relative"].lower() for entry in files}
            for path in folder.rglob("*"):
                nonredirected(path)
                if path.is_file():
                    require(path.relative_to(GAME).as_posix().lower() in known,
                            "Foreign file in owned directory; refusing rollback: " + str(path))


def remove_owned_load_order_entry(contents, original):
    require(b"RainbowBarrels" not in [line.strip() for line in original.splitlines()],
            "RainbowBarrels was not a new owned load-order entry")
    require(b"managed by Vortex" in contents and b"managed by Vortex" in original,
            "Changed load order is not the known Vortex-managed file")
    lines = contents.splitlines(keepends=True)
    owned = [i for i, line in enumerate(lines) if line.strip(b"\r\n") == b"RainbowBarrels"]
    require(len(owned) == 1, "Expected exactly one owned RainbowBarrels line")
    return b"".join(line for i, line in enumerate(lines) if i != owned[0])


def stage(noop_run):
    game_closed()
    noop = noop_confirmed(noop_run)
    plan = preflight()
    stock, original_order, updated_order = baseline(plan)
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    run.mkdir()
    save_new(run / "original.bundle", stock)
    save_new(run / "original.load_order.txt", original_order)
    receipt = {"kind": "candidate", "game_root": str(GAME), "state": "prepared",
               "noop_run": str(noop), "bundle": "bundle/98bb14b1d247a0c8",
               "stock_sha256": STOCK, "installed_sha256": plan["candidate_bundle_sha256"],
               "load_order_before_sha256": sha(original_order), "load_order_after_sha256": sha(updated_order),
               "resources": plan["new_game_resources"], "mod_files": plan["deployed_mod_files"],
               "rollback": "Close Darktide and run deploy_candidate.py restore --run <this directory>. Refuse if Vortex, the game or another tool changed any managed test file."}
    receipt_write(run, receipt)
    try:
        STREAMS.mkdir()
        nonredirected(STREAMS)
        for entry in receipt["resources"]:
            path = GAME / entry["relative"]
            save_new(path, (CANDIDATE / entry["relative"]).read_bytes())
        MOD.mkdir()
        nonredirected(MOD)
        (MOD / "scripts").mkdir()
        (MOD / "scripts/mods").mkdir()
        (MOD / "scripts/mods/RainbowBarrels").mkdir()
        for entry in receipt["mod_files"]:
            relative = entry["relative"].removeprefix("mods/RainbowBarrels/")
            save_new(GAME / entry["relative"], (ROOT / relative).read_bytes())
        replace_exact(ORDER, updated_order, receipt["load_order_before_sha256"])
        replace_exact(GAME_BUNDLE, (CANDIDATE / "bundle/98bb14b1d247a0c8").read_bytes(), STOCK)
        receipt["state"] = "candidate_installed"
        receipt_write(run, receipt)
    except Exception:
        # The prepared receipt and pinned backups permit an explicit safe restore
        # after inspecting the exception; do not hide a partially applied write.
        raise
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "installed_sha256": receipt["installed_sha256"],
                      "rollback": f'python -B "mods/active/RainbowBarrels/resource/deploy_candidate.py" restore --run "{run}"'}, indent=2))


def restore(run):
    game_closed()
    run = run.resolve()
    require(run.parent == RUNS.resolve() and (run / RECEIPT).is_file(), "Unknown deployment run")
    receipt = json.loads((run / RECEIPT).read_text())
    require(receipt["game_root"] == str(GAME) and receipt["kind"] == "candidate",
            "Wrong receipt/game root")
    stock = (run / "original.bundle").read_bytes()
    original_order = (run / "original.load_order.txt").read_bytes()
    require(sha(stock) == STOCK == receipt["stock_sha256"]
            and sha(original_order) == receipt["load_order_before_sha256"], "Deployment backup drift")
    current_bundle = sha(GAME_BUNDLE.read_bytes())
    current_order_bytes = ORDER.read_bytes()
    current_order = sha(current_order_bytes)
    require(current_bundle in (STOCK, receipt["installed_sha256"]),
            "Game bundle was modified by someone else; refusing rollback")
    user_modified_order = current_order not in (receipt["load_order_before_sha256"], receipt["load_order_after_sha256"])
    revised_order = remove_owned_load_order_entry(current_order_bytes, original_order) if user_modified_order else None
    verify_owned_files(receipt)
    if user_modified_order:
        snapshot = run / "vortex-order-before-owned-removal.txt"
        require(not snapshot.exists(), "Previous changed-order snapshot exists")
        save_new(snapshot, current_order_bytes)
        replace_exact(ORDER, revised_order, current_order)
    elif current_order == receipt["load_order_after_sha256"]:
        replace_exact(ORDER, original_order, current_order)
    if current_bundle == receipt["installed_sha256"]:
        replace_exact(GAME_BUNDLE, stock, current_bundle)
    for entry in receipt["resources"] + receipt["mod_files"]:
        path = GAME / entry["relative"]
        if path.exists():
            path.unlink()
    for directory in (MOD / "scripts/mods/RainbowBarrels", MOD / "scripts/mods",
                      MOD / "scripts", MOD, STREAMS):
        if directory.exists():
            directory.rmdir()
    receipt["state"] = "restored"
    receipt["load_order_restored_mode"] = "remove_owned_line_preserving_vortex_changes" if user_modified_order else "original_bytes"
    receipt["load_order_restored_sha256"] = sha(ORDER.read_bytes())
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "stock_bundle_sha256": sha(GAME_BUNDLE.read_bytes()),
                      "load_order_sha256": sha(ORDER.read_bytes())}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage_command = commands.add_parser("stage")
    stage_command.add_argument("--noop-run", type=Path, required=True)
    rollback_command = commands.add_parser("restore")
    rollback_command.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "stage":
        stage(args.noop_run)
    else:
        restore(args.run)
