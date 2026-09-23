"""Decode distinct stock persistent-fire pixel shaders, offline only."""

import hashlib
import json
from pathlib import Path
import subprocess

from profile_shaders import inventory, old


ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "analysis/liquid-stock-24735202"
OUT = ROOT / "analysis/liquid-shaders-24735202"


def main():
    if OUT.exists():
        raise ValueError("Output already exists")
    prepare, _ = old.prior()
    prepare.Dxc()
    tool = prepare.TOOL / "dxc.exe"
    programs = []
    for item in json.loads((STOCK / "materials-provenance.json").read_text())["materials"]:
        if item["shader_bytes"] == 0:
            continue
        source = (STOCK / "materials" / item["retained_file"]).read_bytes()
        if hashlib.sha256(source).hexdigest() != item["stream_sha256"]:
            raise ValueError("Original liquid shader material drift")
        unique = set()
        for index, row in enumerate(inventory(source, include_code=True)):
            if row["stage"] != 0 or row["dxbc_sha256"] in unique:
                continue
            unique.add(row["dxbc_sha256"])
            programs.append((item["identity"], index, row))
    if len(programs) != 9:
        raise ValueError("Unexpected distinct liquid color program count")
    OUT.mkdir(parents=True)
    report = []
    for material, index, row in programs:
        name = material + f"-{index:02d}"
        path = OUT / (name + ".dxbc")
        path.write_bytes(row["dxbc"])
        result = subprocess.run([str(tool), "-dumpbin", str(path)], capture_output=True,
                                timeout=30, check=True)
        if result.stderr or not 0 < len(result.stdout) < 600000:
            raise ValueError("DXC disassembly for stock liquid shader")
        (OUT / (name + ".ll.txt")).write_bytes(result.stdout)
        report.append({"program": name, "material": material, "index": index,
                       "dxbc_sha256": row["dxbc_sha256"],
                       "disassembly_sha256": hashlib.sha256(result.stdout).hexdigest()})
    (OUT / "provenance.json").write_text(json.dumps({"build": "24735202", "status": "offline stock shader research",
                                                  "programs": report}, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
