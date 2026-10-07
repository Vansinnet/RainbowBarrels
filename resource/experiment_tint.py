"""One exact-profile offline shader experiment; no installed resource writes."""

import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from profile_shaders import old


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "analysis/shader-color-trace-24735202/9cda55b98bbfc8ff-01.dxbc"
MANIFEST = ROOT / "analysis/shader-color-trace-24735202/provenance.json"
OUT = ROOT / "analysis/tint-trial-24735202"
STOCK_SHA = "30c3471654fb2507a06b786204173f57a725c7ed6652e7adf8d5a4b5253b4a70"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def chunks(data):
    if data[:4] != b"DXBC" or len(data) < 36:
        raise ValueError("DXBC signature")
    size, count = struct.unpack_from("<II", data, 24)
    if size != len(data) or not 1 <= count <= 16:
        raise ValueError("DXBC directory")
    result = {}
    for i in range(count):
        offset, = struct.unpack_from("<I", data, 32 + i * 4)
        if offset + 8 > len(data):
            raise ValueError("DXBC chunk offset")
        length, = struct.unpack_from("<I", data, offset + 4)
        if offset + 8 + length > len(data):
            raise ValueError("DXBC chunk size")
        tag = data[offset:offset + 4].decode("ascii")
        if tag in result:
            raise ValueError("Duplicate DXBC chunk")
        result[tag] = data[offset + 8:offset + 8 + length]
    if "STAT" not in result or "DXIL" not in result:
        raise ValueError("Missing DXIL/STAT")
    return result


def dump(dxc, path):
    result = subprocess.run([str(dxc), "-dumpbin", str(path)], capture_output=True,
                            timeout=30, check=True)
    if result.stderr or not 0 < len(result.stdout) < 600000:
        raise ValueError("DXC disassembly")
    return result.stdout.decode().replace("\r\n", "\n")


def typed_module(original, stat):
    body = re.search(r"^define void @ps_main\(\) \{\n.*?^\}", original, re.M | re.S)
    if not body or re.findall(r"!\d+", body[0]):
        raise ValueError("Pixel body metadata profile")
    module = stat[stat.index("target datalayout"):]
    if module.count("declare void @ps_main()") != 1:
        raise ValueError("STAT entrypoint")
    if module.count("!2 = !{i32 0, i32 0}") != 1:
        raise ValueError("STAT shader version profile")
    module = module.replace("!2 = !{i32 0, i32 0}", "!2 = !{i32 1, i32 7}")
    counters = re.search(r"^!dx.counters = !\{(!\d+)\}$", module, re.M)
    if counters is None:
        raise ValueError("STAT counters profile")
    module = re.sub(r"^!dx.counters = .*\n", "", module, flags=re.M)
    module = re.sub(r"^" + re.escape(counters[1]) + r" = .*\n", "", module, flags=re.M)
    return module.replace("declare void @ps_main()", body[0])


def tint(module):
    anchor = "  call void @dx.op.storeOutput.f32(i32 5, i32 0, i32 0, i8 0, float %122)"
    if module.count(anchor) != 1:
        raise ValueError("Pixel RGB output anchor")
    body = re.search(r"^define void @ps_main\(\) \{\n.*?^\}", module, re.M | re.S)
    if body is None:
        raise ValueError("Pixel function")
    before, after = body[0].split(anchor, 1)
    if (not before.endswith("  %124 = fmul fast float %121, %52\n")
            or after.count("@dx.op.storeOutput.f32") != 3):
        raise ValueError("Pixel final-color contract changed")
    code = ("  %rb.maxrg = call float @dx.op.binary.f32(i32 35, float %122, float %123)\n"
            "  %rb.value = call float @dx.op.binary.f32(i32 35, float %rb.maxrg, float %124)\n")
    altered = before + code + anchor.replace("float %122)", "float 0.000000e+00)")
    altered += after.replace("i8 1, float %123)", "i8 1, float %rb.value)")
    altered = altered.replace("i8 2, float %124)", "i8 2, float 0.000000e+00)")
    if altered == body[0] or altered.count("%rb.value)") != 1:
        raise ValueError("Pixel color replacement")
    module = module[:body.start()] + altered + module[body.end():]
    if "declare float @dx.op.binary.f32(" not in module:
        module += "\ndeclare float @dx.op.binary.f32(i32, float, float) #0\n"
    return module


def main():
    if OUT.exists():
        raise ValueError("Research output exists")
    source = SOURCE.read_bytes()
    if sha(source) != STOCK_SHA:
        raise ValueError("Original shader identity")
    witness = json.loads(MANIFEST.read_text())
    if not any(p["original_dxbc_sha256"] == STOCK_SHA for p in witness["programs"]):
        raise ValueError("Unsealed shader source")
    prepare, _ = old.prior()
    compiler = prepare.Dxc()
    OUT.mkdir(parents=True)
    stat_file = OUT / "original-STAT.dxil"
    stat_file.write_bytes(chunks(source)["STAT"])
    original = dump(prepare.TOOL / "dxc.exe", SOURCE)
    stat = dump(prepare.TOOL / "dxc.exe", stat_file)
    noop = typed_module(original, stat)
    results = {}
    for mode, text in (("noop", noop), ("fixed-green", tint(noop))):
        assembled, message = compiler.operation(text.encode(), assemble=True)
        if message:
            raise ValueError(f"DXC assembly {mode}: {message}")
        signed, message = compiler.operation(assembled, assemble=False)
        if message or signed[4:20] == bytes(16):
            raise ValueError(f"DXC validation {mode}: {message}")
        (OUT / (mode + ".input.ll")).write_text(text)
        (OUT / (mode + ".dxbc")).write_bytes(signed)
        reflected = dump(prepare.TOOL / "dxc.exe", OUT / (mode + ".dxbc"))
        (OUT / (mode + ".ll.txt")).write_text(reflected)
        if any(chunks(source)[tag] != chunks(signed)[tag] for tag in ("SFI0", "ISG1", "OSG1", "PSV0")):
            raise ValueError("Shader signature changed")
        results[mode] = {"sha256": sha(signed), "bytes": len(signed)}
    (OUT / "report.json").write_text(json.dumps({"source_sha256": STOCK_SHA,
                                                "status": "offline shader candidate; not a game result",
                                                "results": results}, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
