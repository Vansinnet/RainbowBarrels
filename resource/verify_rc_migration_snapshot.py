"""Verify unique recovery snapshot hashes before a broad development rollback."""

import json
from pathlib import Path

from deploy_test import GAME, ROOT, RUNS, nonredirected, sha


SNAPSHOT = RUNS / "20260923T191409Z-1ef8c587-rc-migration-snapshot"
MANIFEST_SHA = "4c2de84586eff9f01bc46e2189270f2d4eb38f649e91481ee55b300631c952ca"


def main():
    raw = (SNAPSHOT / "manifest.json").read_bytes()
    if sha(raw) != MANIFEST_SHA:
        raise ValueError("Development recovery manifest was changed")
    manifest = json.loads(raw)
    if manifest["kind"] != "rc-migration-snapshot" or manifest["game_root"] != str(GAME):
        raise ValueError("Recovery snapshot belongs to a different target")
    total = 0
    for item in manifest["files"]:
        source = SNAPSHOT / "files" / item["relative"]
        nonredirected(source)
        contents = source.read_bytes()
        if len(contents) != item["bytes"] or sha(contents) != item["sha256"]:
            raise ValueError("Snapshot recovery file drift: " + item["relative"])
        total += len(contents)
    if len(manifest["files"]) != 1105 or total != 51628950:
        raise ValueError("Incomplete recovery snapshot")
    print(json.dumps({"snapshot": str(SNAPSHOT), "files_verified": 1105,
                      "bytes_verified": total, "manifest_sha256": MANIFEST_SHA,
                      "status": "recovery-only backup intact; no game files changed"}, indent=2))


if __name__ == "__main__":
    main()
