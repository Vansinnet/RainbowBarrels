"""Read-only byte-level explanation of Vortex-managed load-order drift."""

import hashlib
from difflib import SequenceMatcher
import json
from pathlib import Path

from prepare_deployment import GAME, ROOT
from deploy_candidate import remove_owned_load_order_entry


RUN = ROOT / "analysis/deployment-runs/20260923T074518Z-ac639c88"


def info(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "crlf": data.count(b"\r\n"), "newlines": data.count(b"\n"),
            "utf8_bom": data.startswith(bytes.fromhex("efbbbf")),
            "rainbow_barrels_lines": sum(line.strip() == b"RainbowBarrels" for line in data.splitlines())}


def main():
    current = (GAME / "mods/mod_load_order.txt").read_bytes()
    original = (RUN / "original.load_order.txt").read_bytes()
    deployed = original + (b"" if original.endswith((b"\n", b"\r")) else b"\r\n") + b"RainbowBarrels\r\n"
    first = next((i for i, (left, right) in enumerate(zip(current, deployed)) if left != right), None)
    report = {"current": info(current), "expected_deployed": info(deployed),
              "content_same_after_line_endings": current.splitlines() == deployed.splitlines(),
              "first_different_byte": first}
    old_lines, new_lines = deployed.decode("utf-8-sig").splitlines(), current.decode("utf-8-sig").splitlines()
    changes = []
    for action, i, j, k, l in SequenceMatcher(a=old_lines, b=new_lines).get_opcodes():
        if action != "equal":
            changes.append({"action": action, "old": old_lines[i:j], "current": new_lines[k:l]})
    if len(changes) > 16:
        raise ValueError("Broad load-order drift; inspect manually")
    report["line_changes"] = changes
    stripped = remove_owned_load_order_entry(current, original)
    report["after_owned_line_removal"] = info(stripped)
    report["preserves_every_other_line"] = stripped.splitlines() == [line for line in current.splitlines()
                                                                      if line.strip(b"\r\n") != b"RainbowBarrels"]
    if first is not None:
        report["current_window_hex"] = current[max(0, first - 8):first + 8].hex()
        report["deployed_window_hex"] = deployed[max(0, first - 8):first + 8].hex()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
