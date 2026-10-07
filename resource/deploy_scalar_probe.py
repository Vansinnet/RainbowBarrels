"""Hash-pinned one-file, bounded filled-fire material diagnostic deployment."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import GAME, ROOT, RUNS, game_closed, nonredirected, receipt_write, replace_exact, save_new, sha


BASELINE = "e80157ec1a7f95423584acbe2cd3eb1307c4ce19619050c239c4bdbf4ac8fc38"
LIQUID_BUNDLE = "6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d"
CHILD_STREAMS = {
    "bundle/data/rb/c830ae27aba6f614": "6b36e5b495aff3d258d6044f122ce21354ddc62c6fd322ec7a752947bdbd9190",
    "bundle/data/rb/91db160e1872a6af": "55e69d301287965048bed3c6e689d78f57d1fecc047de5a3659844fe8ceeb6b0",
}
RELATIVE = "mods/RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua"
INSTALLED = GAME / RELATIVE
SOURCE = ROOT / "scripts/mods/RainbowBarrels/RainbowBarrels.lua"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def preflight():
    nonredirected(INSTALLED)
    require(sha(INSTALLED.read_bytes()) == BASELINE, "Installed Lua is not the verified baseline")
    updated = sha(SOURCE.read_bytes())
    require(updated != BASELINE, "Source Lua has no new diagnostic")
    require(sha((GAME / "bundle/b224998193576995").read_bytes()) == LIQUID_BUNDLE,
            "Liquid bundle changed")
    for relative, expected in CHILD_STREAMS.items():
        target = GAME / relative
        nonredirected(target)
        require(sha(target.read_bytes()) == expected, "Child stream changed: " + relative)
    order = GAME / "mods/mod_load_order.txt"
    nonredirected(order)
    contents = order.read_bytes()
    require(sum(line.strip(b"\r\n") == b"RainbowBarrels" for line in contents.splitlines()) == 1,
            "Vortex load order no longer includes exactly one RainbowBarrels")
    return {"previous_sha256": BASELINE, "updated_sha256": updated,
            "vortex_load_order_sha256": sha(contents),
            "scope": "read-only single-file diagnostic preflight; bundles, streams and Vortex list remain unchanged"}


def stage():
    game_closed()
    plan = preflight()
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    run = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + "-scalar-probe")
    run.mkdir()
    save_new(run / "previous.lua", INSTALLED.read_bytes())
    receipt = {"kind": "scalar-probe", "game_root": str(GAME), "state": "prepared",
               "relative": RELATIVE, "previous_sha256": BASELINE,
               "updated_sha256": plan["updated_sha256"],
               "vortex_load_order_sha256_at_stage": plan["vortex_load_order_sha256"],
               "rollback": "Close Darktide and restore only the exact previous Lua file with deploy_scalar_probe.py restore --run <this directory>. Bundle, streams and Vortex list are not owned by this diagnostic."}
    receipt_write(run, receipt)
    replace_exact(INSTALLED, SOURCE.read_bytes(), BASELINE)
    receipt["state"] = "scalar_probe_installed"
    receipt_write(run, receipt)
    print(json.dumps({"run": str(run), "state": receipt["state"],
                      "updated_sha256": plan["updated_sha256"],
                      "bundle_streams_and_load_order_unchanged": True}, indent=2))


def restore(run):
    game_closed()
    run = run.resolve()
    require(run.parent == RUNS.resolve() and (run / "receipt.json").is_file(), "Unknown diagnostic run")
    receipt = json.loads((run / "receipt.json").read_text())
    require(receipt["kind"] == "scalar-probe" and receipt["game_root"] == str(GAME)
            and receipt["relative"] == RELATIVE, "Wrong scalar-probe receipt")
    old = (run / "previous.lua").read_bytes()
    require(sha(old) == receipt["previous_sha256"], "Previous Lua backup changed")
    current = sha(INSTALLED.read_bytes())
    require(current in (receipt["previous_sha256"], receipt["updated_sha256"]),
            "Deployed Lua changed outside this diagnostic")
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
