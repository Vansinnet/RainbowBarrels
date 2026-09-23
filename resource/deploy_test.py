"""Hash-pinned, reversible local game test. Never use backups as development inputs."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

from prepare_deployment import GAME, ROOT, CANDIDATE, OUT as PREP, STOCK


GAME_BUNDLE = GAME / "bundle/98bb14b1d247a0c8"
RUNS = ROOT / "analysis/deployment-runs"
RECEIPT = "receipt.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def game_closed():
    result = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq Darktide.exe", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, timeout=15, check=True)
    require("darktide.exe" not in result.stdout.lower(), "Darktide must be closed before game-file writes")


def nonredirected(path):
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise ValueError("Redirected game path: " + str(path))


def save_new(path, contents):
    nonredirected(path)
    with path.open("xb") as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())
    require(sha(path.read_bytes()) == sha(contents), "New-file readback: " + str(path))


def replace_exact(path, data, expected):
    nonredirected(path)
    require(path.is_file() and sha(path.read_bytes()) == expected, "Refusing changed target: " + str(path))
    staged = path.parent / (".rainbowbarrels-" + uuid.uuid4().hex + ".tmp")
    try:
        save_new(staged, data)
        os.replace(staged, path)
        require(sha(path.read_bytes()) == sha(data), "Replaced-file readback: " + str(path))
    finally:
        if staged.exists():
            staged.unlink()


def receipt_write(run, receipt):
    path = run / RECEIPT
    staged = run / ("." + RECEIPT + ".tmp")
    payload = (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
    try:
        save_new(staged, payload)
        os.replace(staged, path)
    finally:
        if staged.exists():
            staged.unlink()


def preflight():
    plan = json.loads((PREP / "preflight.json").read_text())
    require(plan["game_root"] == str(GAME) and plan["steam_build"] == "24735202", "Preflight build/root")
    require(plan["stock_bundle_sha256"] == STOCK, "Preflight stock identity")
    for parent in (GAME, GAME / "bundle", GAME / "bundle/data", GAME / "mods"):
        nonredirected(parent)
        require(parent.is_dir(), "Required game directory missing: " + str(parent))
    require(plan["candidate_bundle_sha256"] == sha((CANDIDATE / "bundle/98bb14b1d247a0c8").read_bytes()),
            "Candidate bundle changed")
    require(plan["noop_stored_sha256"] == sha((PREP / "98bb14b1d247a0c8.noop.bundle").read_bytes()),
            "No-op bundle changed")
    nonredirected(GAME_BUNDLE)
    require(GAME_BUNDLE.is_file() and sha(GAME_BUNDLE.read_bytes()) == STOCK,
            "Game target must be the stock bundle")
    nonredirected(GAME / "mods/mod_load_order.txt")
    require(sha((GAME / "mods/mod_load_order.txt").read_bytes()) == plan["load_order_sha256"],
            "Vortex load order changed since preflight")
    for item in plan["new_game_resources"]:
        dest = GAME / item["relative"]
        nonredirected(dest)
        require(not dest.exists() and not dest.is_symlink(), "Existing added stream: " + str(dest))
        payload = (CANDIDATE / item["relative"]).read_bytes()
        require(len(payload) == item["bytes"] and sha(payload) == item["sha256"],
                "Material stream drift")
    for item in plan["deployed_mod_files"]:
        dest = GAME / item["relative"]
        nonredirected(dest)
        require(not dest.exists() and not dest.is_symlink(), "Existing deployed mod file: " + str(dest))
        src = ROOT / item["relative"].removeprefix("mods/RainbowBarrels/")
        payload = src.read_bytes()
        require(len(payload) == item["bytes"] and sha(payload) == item["sha256"],
                "Lua mod source drift; rerun read-only preflight")
    require(not (GAME / "bundle/data/rb").exists() and not (GAME / "mods/RainbowBarrels").exists(),
            "Generated game directories must be absent")
    return plan


def stage_noop():
    game_closed()
    plan = preflight()
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    run.mkdir()
    stock = GAME_BUNDLE.read_bytes()
    save_new(run / "original.bundle", stock)
    receipt = {"kind": "noop", "game_root": str(GAME), "state": "prepared",
               "bundle": "bundle/98bb14b1d247a0c8", "stock_sha256": STOCK,
               "installed_sha256": plan["noop_stored_sha256"],
               "backup_sha256": sha(stock),
               "rollback": "Close Darktide; run restore --run <this directory>. Restore only if the installed bundle still has the exact test SHA-256."}
    receipt_write(run, receipt)
    replace_exact(GAME_BUNDLE, (PREP / "98bb14b1d247a0c8.noop.bundle").read_bytes(), STOCK)
    receipt["state"] = "noop_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "installed_sha256": receipt["installed_sha256"],
                      "rollback": f'python -B "mods/active/RainbowBarrels/resource/deploy_test.py" restore --run "{run}"'}, indent=2))


def restore(run):
    game_closed()
    run = run.resolve()
    require(run.parent == RUNS.resolve() and (run / RECEIPT).is_file(), "Unknown owned deployment run")
    receipt = json.loads((run / RECEIPT).read_text())
    require(receipt["game_root"] == str(GAME) and receipt["kind"] == "noop", "Wrong deployment receipt")
    backup = (run / "original.bundle").read_bytes()
    require(sha(backup) == STOCK == receipt["backup_sha256"], "Backup identity changed")
    current = sha(GAME_BUNDLE.read_bytes())
    if current == receipt["installed_sha256"]:
        replace_exact(GAME_BUNDLE, backup, current)
    else:
        require(current == STOCK, "Game bundle changed unexpectedly; refusing rollback")
    receipt["state"] = "restored"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "restored_stock_sha256": sha(GAME_BUNDLE.read_bytes())}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    commands.add_parser("stage-noop")
    restore_command = commands.add_parser("restore")
    restore_command.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        game_closed()
        result = preflight()
        print(json.dumps({"status": "read-only ready", "stock_sha256": STOCK,
                          "new_game_resources": len(result["new_game_resources"])}, indent=2))
    elif args.command == "stage-noop":
        stage_noop()
    elif args.command == "restore":
        restore(args.run)
