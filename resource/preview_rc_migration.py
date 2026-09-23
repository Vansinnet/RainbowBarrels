"""Read-only hash-chain audit before restoring the staged development install."""

import hashlib
import json
from pathlib import Path

from deploy_test import GAME, ROOT, RUNS, nonredirected, sha
from deploy_candidate import remove_owned_load_order_entry


R = "mods/RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua"
GROUND = "bundle/b224998193576995"
EXPLOSION = "bundle/98bb14b1d247a0c8"
STEPS = (
    ("20260923T180023Z-e8e18e29-floor-graph", "floor-graph"),
    ("20260923T172524Z-2c23ccf6-ground-wheel", "ground-wheel"),
    ("20260923T170223Z-1991a1a1-green-children", "green-children"),
    ("20260923T162039Z-fa106e3b-child-only", "child-only"),
    ("20260923T152446Z-3ae58d62-blue-defaults", "blue-defaults"),
    ("20260923T144943Z-edb11c92-scalar-probe", "scalar-probe"),
    ("20260923T142017Z-b17a5aec-child-exports", "child-exports"),
    ("20260923T132814Z-f6c54d3d-fill-fix", "fill-fix"),
    ("20260923T114354Z-7ba643fe-hook-fix", "hook-fix"),
    ("20260923T112114Z-23f7533d-ground-candidate", "ground-candidate"),
    ("20260923T074518Z-ac639c88", "candidate"),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    receipts = {}
    for name, kind in STEPS:
        run = RUNS / name
        item = json.loads((run / "receipt.json").read_text())
        require(item["kind"] == kind and item["game_root"] == str(GAME)
                and item["state"] in ("candidate_installed", "ground_wheel_installed",
                                      "floor_graph_installed", "green_children_installed",
                                      "child_only_installed", "blue_defaults_installed",
                                      "scalar_probe_installed", "child_exports_installed",
                                      "fill_fix_installed", "hook_fix_installed"),
                "Receipt is not the expected owned installation: " + name)
        receipts[kind] = (run, item)
    current = {}
    touched = {GROUND, EXPLOSION, R}
    for _, item in receipts.values():
        for key in ("new_streams", "streams", "resources", "mod_files", "changed_mod_files"):
            touched.update(row["relative"] for row in item.get(key, []))
    for relative in touched:
        path = GAME / relative
        nonredirected(path)
        current[relative] = sha(path.read_bytes()) if path.is_file() else None
    prior = receipts["candidate"][1]
    load_order_path = GAME / "mods/mod_load_order.txt"
    nonredirected(load_order_path)
    load_order = load_order_path.read_bytes()
    revised = remove_owned_load_order_entry(load_order, (receipts["candidate"][0] / "original.load_order.txt").read_bytes())
    require([line for line in revised.splitlines()] ==
            [line for line in load_order.splitlines() if line.strip(b"\r\n") != b"RainbowBarrels"],
            "Vortex-managed unrelated load-order lines would change")

    changes = []

    def move(relative, expected, restored, backup=None):
        require(relative in current and current[relative] == expected,
                "Installed file changed outside the staged sequence: " + relative)
        if backup is not None:
            require(backup.is_file() and sha(backup.read_bytes()) == restored,
                    "Exact rollback backup missing: " + str(backup))
        current[relative] = restored
        changes.append(relative)

    details = []
    for name, kind in STEPS:
        run, receipt = receipts[kind]
        start = len(changes)
        if kind == "floor-graph":
            move(GROUND, receipt["updated_bundle_sha256"], receipt["previous_bundle_sha256"], run / "previous.bundle")
        elif kind == "ground-wheel":
            move(GROUND, receipt["updated_bundle_sha256"], receipt["previous_bundle_sha256"], run / "previous.bundle")
            move(R, receipt["updated_lua_sha256"], receipt["previous_lua_sha256"], run / "previous.lua")
            for row in receipt["new_streams"]:
                move(row["relative"], row["sha256"], None)
        elif kind in ("green-children", "child-only", "blue-defaults", "child-exports"):
            for row in receipt["streams"]:
                move(row["relative"], row["updated_sha256"], row["previous_sha256"],
                     run / Path(row["relative"]).name)
        elif kind in ("scalar-probe", "fill-fix", "hook-fix"):
            old = receipt.get("previous_sha256", receipt.get("deployed_sha256"))
            move(R, receipt["updated_sha256"], old, run / "previous.lua")
        elif kind == "ground-candidate":
            move(GROUND, receipt["installed_sha256"], receipt["stock_sha256"], run / "original.bundle")
            for row in receipt["changed_mod_files"]:
                move(row["relative"], row["new_sha256"], row["deployed_sha256"],
                     run / Path(row["relative"]).name)
            for row in receipt["new_streams"]:
                move(row["relative"], row["sha256"], None)
        else:
            move(EXPLOSION, receipt["installed_sha256"], receipt["stock_sha256"], run / "original.bundle")
            for row in receipt["resources"] + receipt["mod_files"]:
                move(row["relative"], row["sha256"], None)
        details.append({"run": name, "kind": kind, "owned_file_changes": len(changes) - start})

    require(current[GROUND] == receipts["ground-candidate"][1]["stock_sha256"]
            and current[EXPLOSION] == receipts["candidate"][1]["stock_sha256"]
            and current[R] is None,
            "Simulated final bundle/mod state is not stock")
    streams_dir = GAME / "bundle/data/rb"
    require(streams_dir.is_dir(), "Expected owned material stream folder")
    known = {relative for relative in touched if relative.startswith("bundle/data/rb/")}
    for file in streams_dir.iterdir():
        nonredirected(file)
        require(file.is_file() and file.relative_to(GAME).as_posix() in known,
                "Other mod owns an entry in RB material folder: " + str(file))
    require(all(current[relative] is None for relative in known), "Owned material stream remains after planned rollback")
    print(json.dumps({"game_root": str(GAME), "status": "read-only chain complete; no game files changed",
                      "steps_in_required_reverse_order": details,
                      "current_load_order_sha256": hashlib.sha256(load_order).hexdigest(),
                      "after_remove_owned_line_sha256": hashlib.sha256(revised).hexdigest(),
                      "other_load_order_lines_preserved": True,
                      "final_bundles": {GROUND: current[GROUND], EXPLOSION: current[EXPLOSION]},
                      "other_mod_targets_touched": 0,
                      "rollback_source": "eleven pinned development receipts, not the new RC installer"}, indent=2))


if __name__ == "__main__":
    main()
