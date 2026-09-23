"""Hash-pinned one-file test of the VFX-Swapper-compatible filled-fire fix."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import GAME, ROOT, RUNS, game_closed, nonredirected, receipt_write, replace_exact, save_new, sha


PREVIOUS = ROOT / "analysis/deployment-runs/20260923T114354Z-7ba643fe-hook-fix"
RELATIVE = "mods/RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua"
INSTALLED = GAME / RELATIVE
SOURCE = ROOT / "scripts/mods/RainbowBarrels/RainbowBarrels.lua"
LIQUID_BUNDLE = "6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d"
EXPLOSION_BUNDLE = "a0a15fcde68bbd2d7a4ec0cd998bd7d143d2999d3d0b8a74baa60340b529cff9"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def preflight():
    previous = json.loads((PREVIOUS / "receipt.json").read_text())
    require(previous["kind"] == "hook-fix" and previous["state"] == "hook_fix_installed",
            "First hook-order hotfix is not the installed baseline")
    nonredirected(INSTALLED)
    old, new = INSTALLED.read_bytes(), SOURCE.read_bytes()
    require(sha(old) == previous["updated_sha256"] and sha(old) != sha(new),
            "Installed/source Lua SHA-256 no longer forms the expected update")
    require(sha((GAME / "bundle/b224998193576995").read_bytes()) == LIQUID_BUNDLE
            and sha((GAME / "bundle/98bb14b1d247a0c8").read_bytes()) == EXPLOSION_BUNDLE,
            "Previously installed color bundles changed")
    order = (GAME / "mods/mod_load_order.txt").read_bytes()
    require(sum(line.strip(b"\r\n") == b"RainbowBarrels" for line in order.splitlines()) == 1,
            "Vortex load order no longer includes exactly one RainbowBarrels")
    return {"deployed_sha256": sha(old), "updated_sha256": sha(new),
            "deployed_bytes": len(old), "updated_bytes": len(new),
            "vortex_load_order_sha256": sha(order),
            "scope": "read-only one-file hotfix preflight; no game writes"}


def stage():
    game_closed()
    plan = preflight()
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + "-fill-fix")
    run.mkdir()
    save_new(run / "previous.lua", INSTALLED.read_bytes())
    receipt = {"kind": "fill-fix", "game_root": str(GAME), "state": "prepared",
               "relative": RELATIVE, "previous_hotfix_run": str(PREVIOUS),
               "deployed_sha256": plan["deployed_sha256"],
               "updated_sha256": plan["updated_sha256"],
               "vortex_load_order_sha256": plan["vortex_load_order_sha256"],
               "rollback": "Close Darktide, restore the exact previous Lua file with deploy_fill_fix.py restore --run <this directory>. No bundle, stream or Vortex file belongs to this hotfix."}
    receipt_write(run, receipt)
    replace_exact(INSTALLED, SOURCE.read_bytes(), receipt["deployed_sha256"])
    receipt["state"] = "fill_fix_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "updated_sha256": plan["updated_sha256"],
                      "bundle_and_load_order_unchanged": True}, indent=2))


def restore(run):
    game_closed()
    run = run.resolve()
    require(run.parent == RUNS.resolve() and (run / "receipt.json").is_file(), "Unknown owned hotfix run")
    receipt = json.loads((run / "receipt.json").read_text())
    require(receipt["kind"] == "fill-fix" and receipt["game_root"] == str(GAME)
            and receipt["relative"] == RELATIVE, "Wrong fill-fix receipt")
    old = (run / "previous.lua").read_bytes()
    require(sha(old) == receipt["deployed_sha256"], "Prior Lua backup changed")
    current = sha(INSTALLED.read_bytes())
    require(current in (receipt["deployed_sha256"], receipt["updated_sha256"]),
            "Deployed Lua changed outside this hotfix")
    if current == receipt["updated_sha256"]:
        replace_exact(INSTALLED, old, current)
    receipt["state"] = "restored"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "restored_sha256": sha(INSTALLED.read_bytes())}, indent=2))


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
