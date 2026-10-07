"""Disassemble distinct stock pixel shaders in remaining direct and parent materials."""

import hashlib
import json
from pathlib import Path
import subprocess

from profile_shaders import MATERIALS, PARENTS, inventory, old


OUT = Path(__file__).resolve().parents[1] / "analysis" / "shader-remaining-24735202"
DIRECT = {"256482f981ddaf8c", "2e47bba2f141d42a", "be9333164c3ddf4a"}


def main():
    if OUT.exists():
        raise ValueError("Research directory already exists; choose a fresh location")
    prepare, _ = old.prior()
    prepare.Dxc()
    tool = prepare.TOOL / "dxc.exe"
    sources = []
    for item in json.loads((MATERIALS / "provenance.json").read_text())["materials"]:
        if item["identity"] in DIRECT:
            sources.append((MATERIALS / item["material_file"], item["source_sha256"], item["identity"]))
    for item in json.loads((PARENTS / "provenance.json").read_text())["parents"]:
        sources.append((PARENTS / item["extracted_file"], item["sha256"], item["parent"]))
    if len(sources) != 6:
        raise ValueError("Unexpected material count")
    programs = []
    for path, expected, identity in sources:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Material identity changed")
        seen = set()
        for number, frame in enumerate(inventory(data, include_code=True)):
            digest = frame["dxbc_sha256"]
            if frame["stage"] != 0 or digest in seen:
                continue
            seen.add(digest)
            programs.append((identity, number, frame))
    if len(programs) != 19:
        raise ValueError(f"Unexpected unique pixel shader count: {len(programs)}")
    OUT.mkdir(parents=True)
    report = []
    for identity, number, frame in programs:
        stem = f"{identity}-{number:02d}"
        path = OUT / (stem + ".dxbc")
        path.write_bytes(frame["dxbc"])
        disassembly = subprocess.run([str(tool), "-dumpbin", str(path)],
                                     capture_output=True, timeout=30, check=True)
        if disassembly.stderr or not 0 < len(disassembly.stdout) < 600000:
            raise ValueError("DXC output bounds")
        (OUT / (stem + ".ll.txt")).write_bytes(disassembly.stdout)
        report.append({"material": identity, "program": stem, "offset": frame["offset"],
                       "dxbc_sha256": frame["dxbc_sha256"],
                       "disassembly_sha256": hashlib.sha256(disassembly.stdout).hexdigest()})
    (OUT / "provenance.json").write_text(json.dumps({"build": "24735202",
                                                  "status": "offline DXC disassembly; not deployed",
                                                  "programs": report}, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
