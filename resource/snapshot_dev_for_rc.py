"""Capture exact developer-install rollback inputs without altering Darktide."""

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from deploy_test import GAME, ROOT, RUNS, nonredirected, save_new, sha
from preview_rc_migration import STEPS, main as preview


def main():
    preview()
    touched = {"bundle/98bb14b1d247a0c8", "bundle/b224998193576995",
               "mods/mod_load_order.txt", "mods/RainbowBarrels/RainbowBarrels.mod"}
    for name, _ in STEPS:
        receipt = json.loads((RUNS / name / "receipt.json").read_text())
        for key in ("new_streams", "streams", "resources", "mod_files", "changed_mod_files"):
            touched.update(row["relative"] for row in receipt.get(key, []))
    touched.add("mods/RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels.lua")
    RUNS.mkdir(exist_ok=True)
    nonredirected(RUNS)
    snapshot = RUNS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                       "-" + uuid.uuid4().hex[:8] + "-rc-migration-snapshot")
    snapshot.mkdir()
    records = []
    for relative in sorted(touched):
        target = GAME / relative
        nonredirected(target)
        if not target.is_file():
            raise ValueError("Expected installed development input missing: " + relative)
        original = target.read_bytes()
        dest = snapshot / "files" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        save_new(dest, original)
        records.append({"relative": relative, "sha256": sha(original), "bytes": len(original)})
    record = {"kind": "rc-migration-snapshot", "game_root": str(GAME),
              "status": "captured: read-only game access; no game file mutation",
              "files": records,
              "purpose": "Exact recovery input if a separately approved reverse-order development rollback stops partway. Never overlay an installer-owned RC with this snapshot."}
    save_new(snapshot / "manifest.json", (json.dumps(record, indent=2) + "\n").encode())
    print(json.dumps({"snapshot": str(snapshot), "owned_files": len(records),
                      "bytes": sum(item["bytes"] for item in records),
                      "manifest_sha256": sha((snapshot / "manifest.json").read_bytes()),
                      "game_mutated": False}, indent=2))


if __name__ == "__main__":
    main()
