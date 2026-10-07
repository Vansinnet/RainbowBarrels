"""Disassemble selected stock explosion color candidates, offline only."""

import hashlib
import json
from pathlib import Path
import subprocess

from profile_shaders import MATERIALS, inventory, old


OUT = Path(__file__).resolve().parents[1] / "analysis" / "shader-color-trace-24735202"
TARGETS = {"082914d27a058793", "362b6999973734bf", "9cda55b98bbfc8ff",
           "fa7e1d9d2de423bb"}


def main():
    if OUT.exists():
        raise ValueError("Research directory already exists; use a fresh location")
    prepare, _ = old.prior()
    prepare.Dxc()
    tool = prepare.TOOL / "dxc.exe"
    records = json.loads((MATERIALS / "provenance.json").read_text())["materials"]
    payloads = {}
    manifest = []
    for item in records:
        if item["identity"] not in TARGETS:
            continue
        data = (MATERIALS / item["material_file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["source_sha256"]:
            raise ValueError("Material source drift")
        for i, frame in enumerate(inventory(data, include_code=True)):
            if frame["stage"] != 0:
                continue
            name = f"{item['identity']}-{i:02d}"
            payloads[name] = frame
    if len(payloads) != 11:
        raise ValueError(f"Unexpected pixel shader count: {len(payloads)}")
    OUT.mkdir(parents=True)
    for name, frame in payloads.items():
        path = OUT / (name + ".dxbc")
        path.write_bytes(frame["dxbc"])
        result = subprocess.run([str(tool), "-dumpbin", str(path)], capture_output=True,
                                timeout=30, check=True)
        if result.stderr or not 0 < len(result.stdout) < 600000:
            raise ValueError("DXC disassembly result")
        text = OUT / (name + ".ll.txt")
        text.write_bytes(result.stdout)
        manifest.append({"material": name[:16], "program": name, "offset": frame["offset"],
                         "original_dxbc_sha256": frame["dxbc_sha256"],
                         "disassembly_sha256": hashlib.sha256(result.stdout).hexdigest()})
    (OUT / "provenance.json").write_text(json.dumps({"build": "24735202",
                                                  "status": "offline DXC disassembly; not deployed",
                                                  "programs": manifest}, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
