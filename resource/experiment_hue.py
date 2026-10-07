"""One scoped runtime-hue shader candidate; offline DXC validation only."""

import hashlib
import json
from pathlib import Path
import re
import struct

from experiment_tint import MANIFEST, SOURCE, STOCK_SHA, chunks, dump, typed_module
from profile_shaders import old


OUT = Path(__file__).resolve().parents[1] / "analysis" / "hue-trial-24735202"
EXPORT_NAME = "rainbow_barrels_hue"


def f32(value):
    return "0x" + struct.pack(">d", struct.unpack("<f", struct.pack("<f", value))[0]).hex().upper()


def export(module):
    old_type = "%c_material_exports = type { i32, i32, <2 x i32>, <2 x i32>, <2 x i32>, <2 x i32>, <2 x float>, float }"
    if module.count(old_type) != 1:
        raise ValueError("Exact stock material-buffer type")
    module = module.replace(old_type, old_type[:-2] + ", float }")
    old_binding = '%c_material_exports* undef, !"c_material_exports", i32 0, i32 1, i32 1, i32 52, null'
    if module.count(old_binding) != 1:
        raise ValueError("Exact material buffer binding")
    module = module.replace(old_binding, old_binding.replace("i32 52", "i32 56"))
    original = re.search(r"^(!\d+) = !\{i32 52, (!\d+(?:, !\d+)*)\}$", module, re.M)
    if not original or not re.search(r"%c_material_exports undef, " + re.escape(original[1]), module):
        raise ValueError("Material annotation")
    ids = [int(value) for value in re.findall(r"^!(\d+) =", module, re.M)]
    field = max(ids) + 1
    module = module.replace(original[0], f"{original[1]} = !{{i32 56, {original[2]}, !{field}}}")
    module += f'\n!{field} = !{{i32 6, !"{EXPORT_NAME}", i32 3, i32 52, i32 7, i32 9}}\n'
    return module


def color(module):
    anchor = "  call void @dx.op.storeOutput.f32(i32 5, i32 0, i32 0, i8 0, float %122)"
    if module.count(anchor) != 1:
        raise ValueError("Exact stock RGB output")
    instructions = [
        "  %rb.control = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle %4, i32 3)",
        "  %rb.hue = extractvalue %dx.types.CBufRet.f32 %rb.control, 1",
        "  %rb.maxrg = call float @dx.op.binary.f32(i32 35, float %122, float %123)",
        "  %rb.value = call float @dx.op.binary.f32(i32 35, float %rb.maxrg, float %124)",
    ]
    for channel, offset in (("r", 0.0), ("g", 2 / 3), ("b", 1 / 3)):
        prefix = "%rb." + channel
        instructions += [
            f"  {prefix}.shift = fadd float %rb.hue, {f32(offset)}",
            f"  {prefix}.phase = call float @dx.op.unary.f32(i32 22, float {prefix}.shift)",
            f"  {prefix}.six = fmul float {prefix}.phase, 6.000000e+00",
            f"  {prefix}.center = fsub float {prefix}.six, 3.000000e+00",
            f"  {prefix}.abs = call float @dx.op.unary.f32(i32 6, float {prefix}.center)",
            f"  {prefix}.minus = fsub float {prefix}.abs, 1.000000e+00",
            f"  {prefix}.unit = call float @dx.op.unary.f32(i32 7, float {prefix}.minus)",
            f"  %rb.{channel} = fmul float {prefix}.unit, %rb.value",
        ]
    module = module.replace(anchor, "\n".join(instructions) + "\n" + anchor.replace("%122)", "%rb.r)"))
    for component, source, name in ((1, "%123", "g"), (2, "%124", "b")):
        before = f"i8 {component}, float {source})"
        if module.count(before) != 1:
            raise ValueError("Pixel output topology")
        module = module.replace(before, f"i8 {component}, float %rb.{name})")
    if "declare float @dx.op.binary.f32(" not in module:
        module += "\ndeclare float @dx.op.binary.f32(i32, float, float) #0\n"
    return module


def main():
    if OUT.exists():
        raise ValueError("Research output exists")
    original_data = SOURCE.read_bytes()
    if hashlib.sha256(original_data).hexdigest() != STOCK_SHA:
        raise ValueError("Stock shader identity")
    witness = json.loads(MANIFEST.read_text())
    if not any(p["original_dxbc_sha256"] == STOCK_SHA for p in witness["programs"]):
        raise ValueError("Stock shader provenance")
    prepare, _ = old.prior()
    compiler = prepare.Dxc()
    OUT.mkdir(parents=True)
    stat_path = OUT / "original-STAT.dxil"
    stat_path.write_bytes(chunks(original_data)["STAT"])
    original = dump(prepare.TOOL / "dxc.exe", SOURCE)
    stat = dump(prepare.TOOL / "dxc.exe", stat_path)
    typed = typed_module(original, stat)
    candidate = color(export(typed))
    assembled, message = compiler.operation(candidate.encode(), assemble=True)
    if message:
        raise ValueError(f"DXC assembly: {message}")
    signed, message = compiler.operation(assembled, assemble=False)
    if message or signed[4:20] == bytes(16):
        raise ValueError(f"DXC validator: {message}")
    (OUT / "candidate.input.ll").write_text(candidate)
    (OUT / "candidate.dxbc").write_bytes(signed)
    reflected = dump(prepare.TOOL / "dxc.exe", OUT / "candidate.dxbc")
    (OUT / "candidate.ll.txt").write_text(reflected)
    if (len(re.findall(r";\s+float rainbow_barrels_hue;\s*; Offset:\s*52\s*$", reflected, re.M)) != 1
            or any(chunks(original_data)[tag] != chunks(signed)[tag]
                   for tag in ("SFI0", "ISG1", "OSG1", "PSV0"))):
        raise ValueError("Authored reflection/signature mismatch")
    report = {"source_sha256": STOCK_SHA, "candidate_sha256": hashlib.sha256(signed).hexdigest(),
              "candidate_bytes": len(signed), "status": "offline DXC result; material registration untested"}
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
