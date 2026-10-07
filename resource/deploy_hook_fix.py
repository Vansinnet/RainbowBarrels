"""Preflight, stage, and restore one scoped Lua hook-order hotfix."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import GAME, ROOT, RUNS, game_closed, nonredirected, receipt_write, replace_exact, save_new, sha


GROUND_RUN = ROOT / "analysis/deployment-runs/20260923T112114Z-23f7533d-ground-candidate"
RELATIVE = "mods/RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua"
DESTINATION = GAME / RELATIVE
SOURCE = ROOT / "scripts/mods/RainbowBarrels/RainbowBarrels.lua"
EXISTING_BUNDLE = "6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def preflight():
    receipt = json.loads((GROUND_RUN / "receipt.json").read_text())
    if receipt["state"] != "candidate_installed" or receipt["installed_sha256"] != EXISTING_BUNDLE:
        raise ValueError("Ground-fire test receipt is not active")
    current_item = next(row for row in receipt["changed_mod_files"] if row["relative"] == RELATIVE)
    nonredirected(DESTINATION)
    current = DESTINATION.read_bytes()
    proposed = SOURCE.read_bytes()
    if sha(current) != current_item["new_sha256"] or sha(current) == sha(proposed):
        raise ValueError("Installed/source Lua versions are not the intended hotfix pair")
    if sha((GAME / "bundle/b224998193576995").read_bytes()) != EXISTING_BUNDLE:
        raise ValueError("Installed ground-fire package changed unexpectedly")
    mod_order = (GAME / "mods/mod_load_order.txt").read_text(encoding="utf-8-sig").splitlines()
    if sum(line.strip() == "RainbowBarrels" for line in mod_order) != 1:
        raise ValueError("The Vortex-managed mod list no longer loads RainbowBarrels exactly once")
    return {"old_sha256": sha(current), "new_sha256": sha(proposed),
            "old_bytes": len(current), "new_bytes": len(proposed),
            "bundle_sha256": EXISTING_BUNDLE,
            "status": "read-only Lua-only deployment preflight"}


def stage():
    game_closed()
    report = preflight()
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + "-hook-fix")
    run.mkdir()
    old = DESTINATION.read_bytes()
    save_new(run / "previous.lua", old)
    receipt = {"kind": "hook-fix", "state": "prepared", "game_root": str(GAME),
               "relative": RELATIVE, "previous_sha256": report["old_sha256"],
               "updated_sha256": report["new_sha256"], "bundle_sha256": EXISTING_BUNDLE,
               "rollback": "Close Darktide, run deploy_hook_fix.py restore --run <this receipt>. Restore the previous exact Lua bytes only if the deployed copy still matches this hotfix."}
    receipt_write(run, receipt)
    replace_exact(DESTINATION, SOURCE.read_bytes(), receipt["previous_sha256"])
    receipt["state"] = "hook_fix_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "updated_sha256": report["new_sha256"],
                      "bundle_and_vortex_unchanged": True}, indent=2))


def restore(run):
    game_closed()
    run = run.resolve()
    if run.parent != RUNS.resolve() or not (run / "receipt.json").is_file():
        raise ValueError("Unknown owned hotfix deployment run")
    receipt = json.loads((run / "receipt.json").read_text())
    require(receipt["kind"] == "hook-fix" and receipt["game_root"] == str(GAME)
            and receipt["relative"] == RELATIVE, "Wrong hotfix receipt")
    previous = (run / "previous.lua").read_bytes()
    require(sha(previous) == receipt["previous_sha256"], "Lua backup SHA-256 changed")
    current = sha(DESTINATION.read_bytes())
    require(current in (receipt["previous_sha256"], receipt["updated_sha256"]),
            "Deployed Lua changed outside this hotfix")
    if current == receipt["updated_sha256"]:
        replace_exact(DESTINATION, previous, current)
    receipt["state"] = "restored"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "restored_sha256": sha(DESTINATION.read_bytes())}, indent=2))


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
