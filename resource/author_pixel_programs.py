"""Exact-source offline hue-program feasibility check across all barrel materials."""

import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile

from experiment_tint import chunks, dump
from experiment_hue import EXPORT_NAME, f32
from profile_shaders import old


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis/hue-pixel-programs-24735202"
SOURCES = ("shader-color-trace-24735202", "shader-remaining-24735202")
STORE = re.compile(r"call void @dx\.op\.storeOutput\.f32\(i32 5, i32 0, i32 0, i8 ([0-3]), float ([^)]+)\)")


def body(text):
    match = re.search(r"^define void @ps_main\(\) \{\n.*?^\}", text, re.M | re.S)
    if not match:
        raise ValueError("Pixel function definition")
    return match


def module_for(original, stat):
    original, stat = original.replace("\r\n", "\n"), stat.replace("\r\n", "\n")
    executable = body(original)[0]
    module = stat[stat.index("target datalayout"):]
    if module.count("declare void @ps_main()") != 1 or module.count("!2 = !{i32 0, i32 0}") != 1:
        raise ValueError("STAT entrypoint/validator profile")
    module = module.replace("!2 = !{i32 0, i32 0}", "!2 = !{i32 1, i32 7}")
    counters = re.search(r"^!dx.counters = !\{(!\d+)\}$", module, re.M)
    if not counters:
        raise ValueError("STAT counters profile")
    module = re.sub(r"^!dx.counters = .*\n", "", module, flags=re.M)
    module = re.sub(r"^" + re.escape(counters[1]) + r" = .*\n", "", module, flags=re.M)
    definitions = dict(re.findall(r"^!(\d+) = (.*)$", original, re.M))
    references = set(re.findall(r"!(\d+)", executable))
    pending = list(references)
    while pending:
        number = pending.pop()
        definition = definitions.get(number)
        if definition is None or len(references) > 64:
            raise ValueError("Unsupported executable metadata")
        for dependency in re.findall(r"!(\d+)", definition):
            if dependency not in references:
                references.add(dependency)
                pending.append(dependency)
    next_id = 1 + max(map(int, re.findall(r"^!(\d+) =", module, re.M)))
    hints = {number: str(next_id + index) for index, number in enumerate(sorted(references, key=int))}
    for number, substitute in hints.items():
        value = re.sub(r"!(\d+)", lambda match: "!" + hints[match[1]], definitions[number])
        module += f"\n!{substitute} = {value}\n"
    executable = re.sub(r"!(\d+)", lambda match: "!" + hints[match[1]], executable)
    return module.replace("declare void @ps_main()", executable)


def export(module, original):
    reflected = re.search(r";\s*\}\s*c_material_exports;\s*; Offset:\s*0 Size:\s*(\d+)", original)
    binding = re.search(r"; c_material_exports\s+cbuffer\s+NA\s+NA\s+CB\d+\s+cb(\d+)\s+1", original)
    if not reflected or not binding:
        raise ValueError("Material reflection/binding")
    length = int(reflected[1])
    register = int(binding[1])
    definition = re.search(r"^%c_material_exports = type \{(.*)\}$", module, re.M)
    resource = re.search(r'(%c_material_exports\* undef, !"c_material_exports", i32 0, i32 '
                         + str(register) + r', i32 1, i32 )' + str(length) + r'(, null)', module)
    annotation = re.search(r"%c_material_exports undef, (!\d+)", module)
    if not definition or not resource or not annotation:
        raise ValueError("Typed material-buffer profile")
    row = re.search(r"^" + re.escape(annotation[1]) + r" = !\{i32 "
                    + str(length) + r", (.*)\}$", module, re.M)
    if not row:
        raise ValueError("Material field annotations")
    if length % 4 or length < 4:
        raise ValueError("Material field alignment")
    new_id = 1 + max(map(int, re.findall(r"^!(\d+) =", module, re.M)))
    module = module.replace(definition[0], definition[0][:-2] + ", float }")
    module = module.replace(resource[0], resource[1] + str(length + 4) + resource[2])
    row = re.search(r"^" + re.escape(annotation[1]) + r" = !\{i32 "
                    + str(length) + r", (.*)\}$", module, re.M)
    if not row:
        raise ValueError("Material annotations changed during authoring")
    module = module.replace(row[0], f"{annotation[1]} = !{{i32 {length + 4}, {row[1]}, !{new_id}}}")
    module += f'\n!{new_id} = !{{i32 6, !"{EXPORT_NAME}", i32 3, i32 {length}, i32 7, i32 9}}\n'
    handles = re.findall(r"^  (%[\w.]+) = call %dx.types.Handle @dx.op.createHandle\(i32 57, i8 2, i32 "
                         + str(register) + r", i32 " + str(register) + r", i1 false\)", body(original)[0], re.M)
    if len(handles) != 1:
        raise ValueError("Unique material cbuffer handle")
    return module, length, handles[0]


def tint(module, original, offset, handle):
    match = body(module)
    function = match[0]
    stores = STORE.findall(function)
    if len(stores) != 4 or sorted(channel for channel, _ in stores) != list("0123"):
        raise ValueError("Single target RGBA output")
    sources = {int(channel): value for channel, value in stores}
    if not all(re.fullmatch(r"%[\w.]+", sources[i]) for i in range(3)):
        raise ValueError("Color output must have witnessed value definitions")
    anchor = re.search(r"^  call void @dx.op.storeOutput.f32\(i32 5, i32 0, i32 0, i8 0, float "
                       + re.escape(sources[0]) + r"\).*$", function, re.M)
    if not anchor:
        raise ValueError("RGB output anchor")
    register, component = divmod(offset, 16)
    component //= 4
    instructions = [
        f"  %rb.control = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle {handle}, i32 {register})",
        f"  %rb.hue = extractvalue %dx.types.CBufRet.f32 %rb.control, {component}",
        f"  %rb.maxrg = call float @dx.op.binary.f32(i32 35, float {sources[0]}, float {sources[1]})",
        f"  %rb.value = call float @dx.op.binary.f32(i32 35, float %rb.maxrg, float {sources[2]})",
    ]
    for color, turn in (("r", 0.0), ("g", 2 / 3), ("b", 1 / 3)):
        prefix = "%rb." + color
        instructions.extend((
            f"  {prefix}.shift = fadd float %rb.hue, {f32(turn)}",
            f"  {prefix}.phase = call float @dx.op.unary.f32(i32 22, float {prefix}.shift)",
            f"  {prefix}.six = fmul float {prefix}.phase, 6.000000e+00",
            f"  {prefix}.center = fsub float {prefix}.six, 3.000000e+00",
            f"  {prefix}.abs = call float @dx.op.unary.f32(i32 6, float {prefix}.center)",
            f"  {prefix}.minus = fsub float {prefix}.abs, 1.000000e+00",
            f"  {prefix}.unit = call float @dx.op.unary.f32(i32 7, float {prefix}.minus)",
            f"  %rb.{color} = fmul float {prefix}.unit, %rb.value",
        ))
    altered = function[:anchor.start()] + "\n".join(instructions) + "\n" + function[anchor.start():]
    for channel, color in enumerate("rgb"):
        line = re.search(r"^  call void @dx.op.storeOutput.f32\(i32 5, i32 0, i32 0, i8 "
                         + str(channel) + r", float " + re.escape(sources[channel]) + r"\).*$", altered, re.M)
        if not line:
            raise ValueError("Distinct RGB store")
        replacement = line[0].replace("float " + sources[channel] + ")", "float %rb." + color + ")")
        altered = altered[:line.start()] + replacement + altered[line.end():]
    module = module[:match.start()] + altered + module[match.end():]
    for function_name, declaration in (("unary", "declare float @dx.op.unary.f32(i32, float) #0"),
                                       ("binary", "declare float @dx.op.binary.f32(i32, float, float) #0")):
        if "declare float @dx.op." + function_name + ".f32(" not in module:
            module += "\n" + declaration + "\n"
    return module


def check_source(item, folder):
    path = folder / (item["program"] + ".dxbc")
    data = path.read_bytes()
    expected = item.get("original_dxbc_sha256") or item.get("dxbc_sha256")
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("DXBC source identity drift")
    return path, data


def build(sources=SOURCES, output=OUT, expected_count=22):
    if output.exists():
        raise ValueError("Output exists; use a new research directory")
    results = []
    payloads = {}
    prepare, _ = old.prior()
    compiler = prepare.Dxc()
    with tempfile.TemporaryDirectory(dir=Path.home() / "AppData/Local/Temp/opencode") as folder_temp:
        temporary = Path(folder_temp)
        for source in sources:
            folder = ROOT / "analysis" / source
            for item in json.loads((folder / "provenance.json").read_text())["programs"]:
                path, data = check_source(item, folder)
                original = (folder / (item["program"] + ".ll.txt")).read_text()
                if not STORE.findall(body(original)[0]):
                    continue
                try:
                    stat_path = temporary / "source-STAT.dxil"
                    stat_path.write_bytes(chunks(data)["STAT"])
                    stat = dump(prepare.TOOL / "dxc.exe", stat_path)
                    noop = module_for(original, stat)
                    module, offset, handle = export(noop, original)
                    authored = tint(module, original, offset, handle)
                    assembled, message = compiler.operation(authored.encode(), assemble=True)
                    if message:
                        raise ValueError(f"DXC assembly: {message}")
                    validated, message = compiler.operation(assembled, assemble=False)
                    if message or validated[4:20] == bytes(16):
                        raise ValueError(f"DXC validation: {message}")
                    for tag in ("SFI0", "ISG1", "OSG1", "PSV0"):
                        if chunks(data)[tag] != chunks(validated)[tag]:
                            raise ValueError(f"Changed shader signature: {tag}")
                    (temporary / "authored.dxbc").write_bytes(validated)
                    reflected = dump(prepare.TOOL / "dxc.exe", temporary / "authored.dxbc")
                    if len(re.findall(r";\s+float rainbow_barrels_hue;\s*; Offset:\s*"
                                      + str(offset) + r"\s*$", reflected, re.M)) != 1:
                        raise ValueError("Authored hue reflection")
                    results.append({"program": item["program"], "export_offset": offset,
                                    "source_sha256": hashlib.sha256(data).hexdigest(),
                                    "authored_sha256": hashlib.sha256(validated).hexdigest()})
                    payloads[item["program"]] = (authored.encode(), validated)
                except (ValueError, KeyError) as error:
                    raise ValueError(f"{item['program']}: {error}") from error
    if len(results) != expected_count or len(payloads) != expected_count:
        raise ValueError("Unexpected color-program count")
    output.mkdir(parents=True)
    for name, (module, compiled) in payloads.items():
        (output / (name + ".input.ll")).write_bytes(module)
        (output / (name + ".dxbc")).write_bytes(compiled)
    (output / "provenance.json").write_text(json.dumps({"build": "24735202",
                                                  "status": "offline signed shader candidates; not registered or deployed",
                                                  "programs": results}, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    build()
