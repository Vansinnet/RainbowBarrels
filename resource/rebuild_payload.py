"""Rebuild the whole RainbowBarrels payload from the installed game's stock files.

Run this after every Darktide update that `reforge verify` reports as changed:

    python mods/active/RainbowBarrels/resource/rebuild_payload.py
    tools\\reforge\\reforge.cmd build mods\\active\\RainbowBarrels --game "<game folder>"

It reads the two stock bundles named in reforge.json and the material streams they point to,
regenerates payload/bundles/<both> and all 1,098 payload/materials streams, and pins the new
stock bundle hashes in reforge.json (keeping `late_load`). Nothing is pinned to a game build;
every target is found by name hash and structure:

* Explosion bundle 98bb14b1d247a0c8: particles `frag_grenade_01` (explosive barrel) and
  `explosive_barrel_explosion` (fire barrel). Their billboard (type-0) clouds name the materials;
  shaderless children lead to their parents. Every shader-bearing material gets a
  `rainbow_barrels_hue` scalar (template, registration, GPU default; a full material buffer grows
  by 16 bytes) and every colour-writing pixel program becomes hue-controlled (DXC). Children only
  point at the custom parent. Each particle is cloned 360 times with renamed clouds, custom
  materials and the two type-1 light ColorGraphs recoloured to that hue.
* Ground bundle b224998193576995: particles `liquid_area/fire_lingering` (filled) and
  `fire_lingering_edge` (rim). The same material treatment, plus a hue scalar on the two
  shaderless children; 360 filled/rim clones bind per-hue materials (children: template value,
  rim: template and GPU default) and the filled clone's type-2 floor ColorGraph is recoloured.

Every step checks its anchors and stops on anything unexpected (a new material or shader
version, moved clouds or curves, a changed program pattern, a no-op rebuild that does not
reproduce stock); that is the point to read RESEARCH.md again. A report is written to
analysis/rebuild-<stock hashes>/report.json.

Tools: the game's Oodle library (through tools/reforge/cli/bundle8.py) and Microsoft's DXC in
tools/dxc/bin/x64 (dxcompiler.dll and dxc.exe; override with RB_DXC). Windows only.
"""
import argparse
import ctypes as C
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
MOD = HERE.parent
WORKSPACE = MOD.parents[2]
sys.path.insert(0, str(WORKSPACE / "tools/reforge/cli"))
import bundle8  # noqa: E402

GAME = Path(r"D:\Steam\steamapps\common\Warhammer 40,000 DARKTIDE")
DXC = Path(os.environ.get("RB_DXC", WORKSPACE / "tools/dxc/bin/x64"))
MATERIAL_VERSIONS = {61, 62}
SHADER_VERSION = 43
PARTICLE_VERSION = 102
EXPLOSION = "bundle/98bb14b1d247a0c8"
GROUND = "bundle/b224998193576995"
CUSTOM = "content/fx/materials/rainbow_barrels/"
EXPORT_NAME = "rainbow_barrels_hue"
ANCHOR_HASH = 0x2CC3DCEE  # a field of every material's c_material_exports registration
HUES = range(360)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Fail(Exception):
    pass


def need(condition, message):
    if not condition:
        raise Fail(message)


def murmur64(text):
    data = text.encode() if isinstance(text, str) else text
    m, mask = 0xc6a4a7935bd1e995, (1 << 64) - 1
    value = len(data) * m & mask
    end = len(data) // 8 * 8
    for (word,) in struct.iter_unpack("<Q", data[:end]):
        word = word * m & mask
        word ^= word >> 47
        value = (value ^ (word * m & mask)) * m & mask
    if data[end:]:
        value = (value ^ int.from_bytes(data[end:], "little")) * m & mask
    value ^= value >> 47
    value = value * m & mask
    return value ^ (value >> 47)


PARTICLES = murmur64("particles")
MATERIAL = murmur64("material")
HASH32 = murmur64(EXPORT_NAME) >> 32
MATERIAL_BUFFER = murmur64("c_material_exports") >> 32


# ---- DXC (COM through ctypes; one calling convention on x64) ----

P, H, U = C.c_void_p, C.c_int32, C.c_uint32


def _method(obj, slot, result, *types):
    table = C.cast(obj, C.POINTER(C.POINTER(P))).contents
    return C.CFUNCTYPE(result, P, *types)(table[slot])


def _release(obj):
    if obj:
        _method(obj, 2, U)(obj)


def _check(hr):
    if hr < 0:
        raise Fail(f"DXC HRESULT 0x{hr & 0xffffffff:08x}")


def _blob_bytes(blob):
    if not blob:
        return b""
    size = _method(blob, 4, C.c_size_t)(blob)
    need(size <= 2_000_000, "DXC blob too large")
    return C.string_at(_method(blob, 3, P)(blob), size)


class Dxc:
    """IDxcAssembler and IDxcValidator from dxcompiler.dll (the validator signs the container)."""

    def __init__(self, folder=DXC):
        need((folder / "dxcompiler.dll").is_file() and (folder / "dxc.exe").is_file(),
             f"DXC not found in {folder} (set RB_DXC)")
        os.add_dll_directory(str(folder))
        self.folder = folder
        self.lib = C.CDLL(str(folder / "dxcompiler.dll"))
        self.version = subprocess.run([str(folder / "dxc.exe"), "--version"], capture_output=True,
                                      timeout=30).stdout.decode().strip()

    def _create(self, clsid, iid):
        fn = self.lib.DxcCreateInstance
        fn.argtypes, fn.restype = [P, P, C.POINTER(P)], H
        c, i = (C.create_string_buffer(uuid.UUID(x).bytes_le) for x in (clsid, iid))
        obj = P()
        _check(fn(c, i, C.byref(obj)))
        need(obj, "DXC returned no object")
        return obj

    def _blob(self, data):
        need(0 < len(data) <= 900_000, "DXC input out of bounds")
        utils = self._create("6245d6af-66e0-48fd-80b4-4d271796748c", "4605c4cb-2019-492a-ada4-65f20bb7d67f")
        blob = P()
        try:
            self._memory = C.create_string_buffer(data)
            _check(_method(utils, 6, H, P, U, U, C.POINTER(P))(utils, self._memory, len(data), 0, C.byref(blob)))
            return blob
        finally:
            _release(utils)

    def _operation(self, data, assemble):
        blob, obj, res, out, err = self._blob(data), P(), P(), P(), P()
        try:
            if assemble:
                obj = self._create("d728db68-f903-4f80-94cd-dccf76ec7151", "091f7a26-1c1f-4948-904b-e6e3a8a771d5")
                _check(_method(obj, 3, H, P, C.POINTER(P))(obj, blob, C.byref(res)))
            else:
                obj = self._create("8ca3e215-f728-4cf3-8cdd-88af917587a1", "a6e82bd2-1fd7-4826-9811-2857e797f49a")
                _check(_method(obj, 3, H, P, U, C.POINTER(P))(obj, blob, 0, C.byref(res)))
            status = H()
            _check(_method(res, 3, H, C.POINTER(H))(res, C.byref(status)))
            _check(_method(res, 5, H, C.POINTER(P))(res, C.byref(err)))
            message = _blob_bytes(err).decode("utf-8", "replace").rstrip("\0")
            need(status.value >= 0, f"DXC operation failed: {message}")
            _check(_method(res, 4, H, C.POINTER(P))(res, C.byref(out)))
            return _blob_bytes(out), message
        finally:
            for item in (err, out, res, obj, blob):
                _release(item)

    def compile(self, module):
        """LLVM IR text -> validated, signed DXBC container."""
        encoded, warning = self._operation(module.encode(), assemble=True)
        need(not warning, "DXC assembly warning: " + warning)
        signed, warning = self._operation(encoded, assemble=False)
        need(not warning and signed[4:20] != bytes(16), "DXC validation failed: " + warning)
        return signed

    def dump(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "program.bin"
            path.write_bytes(data)
            result = subprocess.run([str(self.folder / "dxc.exe"), "-dumpbin", str(path)],
                                    capture_output=True, timeout=60)
        need(result.returncode == 0 and not result.stderr and 0 < len(result.stdout) <= 2_000_000,
             "DXC disassembly failed: " + result.stderr.decode("utf-8", "replace"))
        return result.stdout.decode().replace("\r\n", "\n")


# ---- Bundles ----

def read_bundle(data, oodle):
    """(256-byte header block, [(index row, raw record)]) of a format-8 bundle."""
    layout = bundle8.parse(data)
    full = b"".join(b if len(b) == bundle8.CHUNK else oodle.decompress(b) for b in layout.blocks)
    stream, tail = full[:layout.length], full[layout.length:]
    need(not any(tail), "nonzero bundle padding")
    count, = struct.unpack_from("<I", data, 8)
    index = list(struct.iter_unpack("<QQI", data[268:268 + 20 * count]))
    cursor, records = 0, []
    for row in index:
        start = cursor
        kind, name, variants, zero = struct.unpack_from("<QQII", stream, cursor)
        need((kind, name) == row[:2] and zero == 0 and 1 <= variants <= 64, "bundle record identity")
        cursor += 24
        descriptors = [struct.unpack_from("<IBIBI", stream, cursor + 14 * i) for i in range(variants)]
        cursor += 14 * variants
        cursor += sum(d[2] + d[4] for d in descriptors)
        need(cursor <= len(stream), "bundle record bounds")
        records.append((row, stream[start:cursor]))
    need(cursor == len(stream), "unconsumed bundle bytes")
    return data[12:268], records


def write_bundle(opaque, records):
    """Stored-chunk bundle (the layout the 1.0 payload was authored in); packed afterwards."""
    need(len({row[:2] for row, _ in records}) == len(records), "duplicate bundle identity")
    logical = b"".join(raw for _, raw in records)
    count = math.ceil(len(logical) / bundle8.CHUNK)
    payload = logical + bytes(count * bundle8.CHUNK - len(logical))
    out = bytearray(bundle8.MAGIC + struct.pack("<I", len(records)) + opaque)
    for row, _ in records:
        out += struct.pack("<QQI", *row)
    out += struct.pack("<I", count) + struct.pack("<I", bundle8.CHUNK) * count
    out += bytes((-len(out)) % 16) + struct.pack("<II", len(logical), 0)
    for i in range(count):
        out += struct.pack("<I", bundle8.CHUNK)
        out += bytes((-len(out)) % 16) + payload[i * bundle8.CHUNK:(i + 1) * bundle8.CHUNK]
    return bytes(out)


def single_body(raw):
    """Body of a one-variant record (particles, material pointers)."""
    variants, = struct.unpack_from("<I", raw, 16)
    need(variants == 1, "multi-variant record")
    _, flag, size, one, tail = struct.unpack_from("<IBIBI", raw, 24)
    need(one == 1 and tail == 0 and 38 + size == len(raw), "record descriptor")
    return flag, raw[38:]


def streamed_record(kind, name, body):
    return struct.pack("<QQII", kind, name, 1, 0) + struct.pack("<IBIBI", 0, 1, len(body), 1, 0) + body


def find(records, kind, name):
    hits = [raw for row, raw in records if row[:2] == (kind, name)]
    need(len(hits) == 1, f"resource {name:016x} found {len(hits)} times")
    return hits[0]


def material_stream(records, name, stock_root):
    flag, body = single_body(find(records, MATERIAL, name))
    path = body.split(b"\0", 1)[0].decode("ascii")
    need(flag == 1 and re.fullmatch(r"data/[0-9a-f]{2}/[0-9a-f]{16}", path), f"material {name:016x} is not streamed")
    return "bundle/" + path, (stock_root / "bundle" / path).read_bytes()


# ---- Particles ----

def profile(data):
    need(len(data) >= 82 and struct.unpack_from("<I", data, 38)[0] == PARTICLE_VERSION,
         "particle version changed")
    body = data[38:]
    variables, count = struct.unpack_from("<II", body, 36)
    need(variables <= 64 and count <= 64, "particle cloud count")
    offset, rows = 44 + variables * 16, []
    for index in range(count):
        need(offset + 576 <= len(body), "cloud header bounds")
        words = struct.unpack_from("<144I", body, offset)
        slots, stride = words[3:5]
        need(slots <= 16 and sum(words[5:5 + slots]) == stride, "cloud slot layout")
        sections = [words[i] for i in (134, 136, 137, 140, 143)]
        need(576 <= sections[0] <= sections[1] <= sections[2] <= sections[3] <= sections[4] <= len(body) - offset,
             "cloud sections")
        visualizer = offset + sections[3]
        end = offset + sections[4]
        rows.append({"index": index, "cloud_id": words[0],
                     "type": struct.unpack_from("<I", body, visualizer)[0] if visualizer + 4 <= end else None,
                     "material": (struct.unpack_from("<Q", body, visualizer + 12)[0]
                                  if slots and visualizer + 20 <= end else None),
                     "body": 38 + offset, "visualizer": 38 + visualizer, "visualizer_size": end - visualizer})
        offset = end
    need(offset == len(body), "unconsumed particle body")
    return rows


def color_graphs(data):
    """ColorGraph-shaped spans: mode, ten times, ten RGB keys, active key count."""
    result = []
    for offset in range(0, len(data) - 168 + 1, 4):
        mode, = struct.unpack_from("<I", data, offset)
        if not 0 <= mode <= 12:
            continue
        times = struct.unpack_from("<10f", data, offset + 4)
        values = struct.unpack_from("<30f", data, offset + 44)
        keys, = struct.unpack_from("<I", data, offset + 164)
        if (not 2 <= keys <= 10 or any(not math.isfinite(v) for v in times + values)
                or times[0] != 0 or times[keys - 1] > 1
                or any(a >= b for a, b in zip(times[:keys - 1], times[1:keys]))
                or not all(t >= 10000 for t in times[keys:]) or not all(0 <= v <= 10050 for v in values)):
            continue
        result.append({"offset": offset, "mode": mode, "keys": keys,
                       "rgb": [values[3 * i:3 * i + 3] for i in range(keys)]})
    return result


def rgb(hue):
    phase = hue / 60
    x = 1 - abs(phase % 2 - 1)
    return ((1, x, 0), (x, 1, 0), (0, 1, x), (0, x, 1), (x, 0, 1), (1, 0, x))[int(phase) % 6]


def light_graphs(source):
    """The type-1 light clouds' ColorGraphs: [(absolute RGB offset, key count)]."""
    found = []
    for row in profile(source):
        if row["type"] != 1:
            continue
        need(row["visualizer_size"] == 692, f"light visualizer of cloud {row['index']} changed size")
        start = row["visualizer"]
        graphs = color_graphs(source[start:start + 692])
        need(len(graphs) == 1 and graphs[0]["offset"] == 352, f"light ColorGraph of cloud {row['index']} moved")
        found.append({"cloud": row["index"], "rgb": start + 352 + 44, "keys": graphs[0]["keys"],
                      "mode": graphs[0]["mode"]})
    need(len(found) == 2, f"expected two light clouds, found {len(found)}")
    return found


def recolor_lights(source, graphs, hue):
    result = bytearray(source)
    for graph in graphs:
        for key in range(graph["keys"]):
            offset = graph["rgb"] + 12 * key
            old = struct.unpack_from("<3f", source, offset)
            struct.pack_into("<3f", result, offset, *(max(old) * c for c in rgb(hue)))
    return bytes(result)


FLOOR_RGB = ((0.0, 0.0, 0.0), (255.0, 255.0, 255.0), (229.0, 229.0, 229.0), (0.0, 0.0, 0.0))


def floor_graph(source):
    """Absolute offsets of the filled fire's type-2 (floor) ColorGraph's two lit keys."""
    rows = [row for row in profile(source) if row["type"] == 2]
    need(len(rows) == 1 and rows[0]["visualizer_size"] == 728, "filled fire type-2 visualizer changed")
    start = rows[0]["visualizer"]
    graphs = color_graphs(source[start:start + 728])
    need(len(graphs) == 1 and graphs[0]["offset"] == 480 and graphs[0]["mode"] == 3
         and tuple(map(tuple, graphs[0]["rgb"])) == FLOOR_RGB, "floor ColorGraph changed")
    return [(start + 480 + 44 + 12 * key, FLOOR_RGB[key][0]) for key in (1, 2)]


def clone_particle(source, effect, name, clouds, materials):
    """Rename the particle and its billboard clouds and rebind their materials."""
    rows = profile(source)
    result = bytearray(source)
    need(struct.unpack_from("<Q", source, 8)[0] == murmur64(effect), "particle identity changed")
    struct.pack_into("<Q", result, 8, murmur64(name))
    existing = {row["cloud_id"] for row in rows}
    touched = []
    for row in rows:
        if row["type"] != 0 or not row["material"]:
            continue
        need(row["material"] in materials, f"unmapped billboard material {row['material']:016x}")
        struct.pack_into("<Q", result, row["visualizer"] + 12, materials[row["material"]])
        cloud = murmur64(f"RainbowBarrels_{clouds}_{row['index']:02d}") >> 32
        need(cloud not in existing, "cloud identifier collision")
        struct.pack_into("<I", result, row["body"], cloud)
        touched += [(8, 8), (row["visualizer"] + 12, 8), (row["body"], 4)]
    need(touched, "particle has no billboard clouds")
    restored = bytearray(result)
    for offset, size in touched:
        restored[offset:offset + size] = source[offset:offset + size]
    need(restored == source, "particle edit touched other bytes")
    return bytes(result)


# ---- Materials ----

class Cursor:
    def __init__(self, data, pos=0):
        self.data, self.pos = data, pos

    def take(self, size):
        need(0 <= size <= len(self.data) - self.pos, "material section boundary")
        self.pos += size
        return self.data[self.pos - size:self.pos]

    def words(self, count=1):
        return struct.unpack("<" + "I" * count, self.take(4 * count))

    def table(self, width):
        count, = self.words()
        need(count <= 4096, "material table count")
        return [self.words(width) for _ in range(count)]


def pack_words(values):
    return struct.pack("<" + "I" * len(values), *values)


def pack_table(rows):
    return pack_words((len(rows),)) + b"".join(pack_words(row) for row in rows)


def envelope(data):
    version, mo, ms, so, ss, tail, ts = struct.unpack_from("<7I", data)
    need(version in MATERIAL_VERSIONS, f"material version {version} is new; check the format before adding it")
    need(mo == 28 and mo + ms <= len(data), "material envelope changed")
    if so != 0xFFFFFFFF:
        need(so == mo + ms and so + ss <= len(data), "material shader section moved")
    if tail != 0xFFFFFFFF:
        need(tail == so + ss and tail + ts == len(data), "material tail section moved")
    return mo, ms, so, ss, tail


def template(block, append):
    """Material template; append adds a zero `rainbow_barrels_hue` reflection row and value."""
    c = Cursor(block)
    head = c.take(20)
    tables = [c.table(width) for width in (1, 3, 2, 5)]
    values = c.take(c.words()[0])
    count, = c.words()
    opaque = c.take(count * 5)
    last = c.table(2)
    need(c.pos == len(block), "material template exhaustion")
    if append:
        need(not any(row[2] == HASH32 for row in tables[3]), "material already exports the hue")
        tables[3].append((0, 0, HASH32, len(values), 4))
        values += struct.pack("<f", 0)
    result = (head + b"".join(pack_table(t) for t in tables) + pack_words((len(values),)) + values
              + pack_words((count,)) + opaque + pack_table(last))
    need(append or result == block, "material template no-op roundtrip")
    return result, tables[3], len(values)


def defaults(data):
    c = Cursor(data)
    need(c.words() == (0,), "shader defaults prefix")
    rows = []
    for key, width, offset in c.table(3):
        need(width in (1, 2, 3, 4) and c.pos == offset, "shader default offset")
        rows.append((key, c.take(4 * width)))
    need(not any(data[c.pos:]) and len(data) - c.pos <= 15, "shader defaults padding")
    need(data == encode_defaults(rows) + bytes(len(data) - c.pos), "shader defaults roundtrip")
    return rows


def encode_defaults(rows):
    descriptors, values, offset = [], b"", 8 + 12 * len(rows)
    for key, value in rows:
        descriptors.append((key, len(value) // 4, offset))
        values += value
        offset += len(value)
    return pack_words((0,)) + pack_table(descriptors) + values


def registration(data, offset, full):
    """Shader groups; register the hue at `offset` in every material buffer (growing it if full)."""
    c = Cursor(data)
    count, = c.words()
    need(1 <= count <= 32, "shader group count")
    result, changed = pack_words((count,)), 0
    for _ in range(count):
        key, allocation = c.words(2)
        resources = c.table(4)
        n, = c.words()
        need(1 <= n <= 16, "material buffer count")
        buffers = []
        for _ in range(n):
            rows = c.table(5)
            size, start = c.words(2)
            buffers.append([rows, size, start])
        targets = [i for i, (rows, _, _) in enumerate(buffers) if any(r[2] == ANCHOR_HASH for r in rows)]
        need(len(targets) <= 1, "two material buffers in one group")
        for i in targets:
            rows, size, start = buffers[i]
            used = max(r[3] + max(1, r[1]) * r[4] for r in rows)
            need(not any(r[2] == HASH32 for r in rows), "material buffer already has the hue")
            if full:
                need(i == 3 and size == used == offset, "full material buffer layout changed")
                need(allocation == max(o + s for _, s, o in buffers if o > 0 and s < 1024),
                     "buffer allocation extent")
                rows.append((0, 0, HASH32, offset, 4))
                buffers[i][1] = size + 16
                for later in buffers[i + 1:]:
                    need(later[2] >= start + size, "unmapped buffer relocation")
                    later[2] += 16
                allocation += 16
            else:
                need(any(r[3] + r[4] == offset for r in rows) and offset + 4 <= size,
                     "material buffer end does not match the shader reflection")
                rows.append((0, 0, HASH32, offset, 4))
            changed += 1
        part = pack_words((key, allocation)) + pack_table(resources) + pack_words((n,))
        for rows, size, start in buffers:
            need(all(r[3] + max(1, r[1]) * r[4] <= size for r in rows), "buffer descriptor extent")
            part += pack_table(rows) + pack_words((size, start))
        associations = c.table(7)
        techniques, = c.words()
        need(techniques <= 64, "technique count")
        part += pack_table(associations) + pack_words((techniques,)) + c.take(17 * techniques + 8)
        result += part
    need(c.pos == len(data) and changed >= 1, "shader registration exhaustion or no material buffer")
    return result, changed


def metadata_end(shader, start, stop):
    need(start + 16 <= stop and struct.unpack_from("<I", shader, start)[0] == 5, "shader program metadata")
    cursor = start + 16
    for width in (6, 0, 0, 7, 7, 7, 7, 4, 3, 3):
        count, = struct.unpack_from("<I", shader, cursor)
        need(count <= 512 and not (width == 0 and count) and cursor + 4 + 4 * width * count <= stop,
             "shader metadata table")
        cursor += 4 + 4 * width * count
    return cursor


def dxbc_stage(program):
    need(program[:4] == b"DXBC" and len(program) >= 36, "program is not DXBC")
    size, count = struct.unpack_from("<II", program, 24)
    need(size == len(program) and 1 <= count <= 16, "DXBC directory")
    stages = set()
    for i in range(count):
        offset, = struct.unpack_from("<I", program, 32 + 4 * i)
        if program[offset:offset + 4] == b"DXIL":
            stages.add(struct.unpack_from("<I", program, offset + 8)[0] >> 16)
    need(len(stages) == 1, "DXIL stage count")
    return stages.pop()


def dxbc_parts(program):
    _, count = struct.unpack_from("<II", program, 24)
    parts = {}
    for i in range(count):
        offset, = struct.unpack_from("<I", program, 32 + 4 * i)
        size, = struct.unpack_from("<I", program, offset + 4)
        parts[program[offset:offset + 4].decode("ascii")] = program[offset + 8:offset + 8 + size]
    return parts


def frames(shader, start, stop, oodle):
    cursor, found = start, []
    while (begin := shader.find(b"\x8c\x06", cursor, stop)) != -1:
        cursor = begin + 2
        if begin < start + 8 or begin + 5 > stop:
            continue
        tag, encoded = struct.unpack_from("<II", shader, begin - 8)
        finish = begin + encoded
        if tag != 1 or not begin + 8 <= finish <= stop - 16:
            continue
        frame = shader[begin:finish]
        if int.from_bytes(frame[2:5], "big") + 1 != len(frame) - 5:
            continue
        kind, decoded, key = struct.unpack_from("<IIQ", shader, finish)
        if kind != 5 or not 32 <= decoded <= 262144 or murmur64(frame) != key:
            continue
        end = metadata_end(shader, finish, stop)
        program = frame[5:] if len(frame) - 5 == decoded else oodle.decompress(frame, decoded)
        need(len(program) == decoded, "Kraken decoded length")
        found.append({"envelope": begin - 8, "finish": finish, "end": end, "program": program,
                      "sha256": sha(program), "stage": dxbc_stage(program)})
        cursor = end
    need(found, "no shader programs found")
    return found


def shader_layout(data, oodle):
    mo, ms, so, ss, tail = envelope(data)
    need(so != 0xFFFFFFFF, "material has no shader")
    shader = data[so:so + ss]
    head = struct.unpack_from("<12I", shader)
    start, group_size, device, device_size = head[8:12]
    need(head[0] == SHADER_VERSION, f"shader version {head[0]} is new; check the format before adding it")
    need(48 <= start < start + group_size <= device < device + device_size <= head[5] <= len(shader),
         "shader section bounds")
    gap = shader[start + group_size:device]
    need(not any(gap) and len(gap) == (-start - group_size) % 4, "group/device alignment")
    need(not any(shader[device + device_size:head[5]]), "pre-default padding")
    return shader, start, group_size, device, device_size, head[5], frames(shader, device, device + device_size, oodle)


def author_shader_material(data, replacements, offset, oodle):
    """Add the hue scalar and swap programs; `replacements` maps stock program SHA-256 -> DXBC."""
    mo, ms, so, ss, tail = envelope(data)
    shader, start, group_size, device, device_size, default_at, programs = shader_layout(data, oodle)
    _, _, values_size = template(data[mo:so], False)
    groups_before = shader[start:start + group_size]
    # A material buffer without room for one more scalar grows by one 16-byte register.
    full = not registration_fits(groups_before, offset)
    groups, registered = registration(groups_before, offset, full)
    material, _, _ = template(data[mo:so], True)
    values = defaults(shader[default_at:])
    need(not any(key == HASH32 for key, _ in values), "shader default already has the hue")
    values.append((HASH32, struct.pack("<f", 0)))
    pieces, previous, swapped, resized = [], device, [], 0
    for i, frame in enumerate(programs):
        pieces.append(shader[previous:frame["envelope"]])
        metadata = bytearray(shader[frame["finish"]:frame["end"]])
        new = replacements.get(frame["sha256"])
        if new is None:
            encoded = shader[frame["envelope"] + 8:frame["finish"]]
        else:
            need(32 <= len(new) <= 262143, "replacement program size")
            encoded = b"\x8c\x06" + (len(new) - 1).to_bytes(3, "big") + new
            struct.pack_into("<IQ", metadata, 4, len(new), murmur64(encoded))
            swapped.append(i)
        if full:
            rows, = struct.unpack_from("<I", metadata, 16)
            for row in range(rows):
                at = 20 + 24 * row
                name, _, size = struct.unpack_from("<III", metadata, at)
                if name == MATERIAL_BUFFER:
                    need(size == offset, "program material-buffer size")
                    struct.pack_into("<I", metadata, at + 8, offset + 16)
                    resized += 1
        pieces += [pack_words((1, len(encoded))), encoded, bytes(metadata)]
        previous = frame["end"]
    pieces.append(shader[previous:device + device_size])
    need(swapped, "no colour program replaced")
    need(not full or resized >= len(swapped), "hue program without a resized material buffer")
    new_device = b"".join(pieces)
    new_start = start + len(groups) + (-start - len(groups)) % 4
    new_default = (new_start + len(new_device) + 3) & ~3
    head = bytearray(shader[:start])
    struct.pack_into("<I", head, 20, new_default)
    struct.pack_into("<I", head, 36, len(groups))
    struct.pack_into("<II", head, 40, new_start, len(new_device))
    rebuilt = (bytes(head) + groups + bytes(new_start - start - len(groups)) + new_device
               + bytes(new_default - new_start - len(new_device)) + encode_defaults(values))
    rebuilt += bytes((-len(rebuilt)) % 16)
    outer = bytearray(data[:28])
    struct.pack_into("<III", outer, 8, len(material), 28 + len(material), len(rebuilt))
    if tail != 0xFFFFFFFF:
        struct.pack_into("<I", outer, 20, 28 + len(material) + len(rebuilt))
    result = bytes(outer) + material + rebuilt + data[so + ss:]
    return result, {"full_buffer": full, "registered_buffers": registered, "programs": len(programs),
                    "swapped_frames": swapped, "resized_metadata_rows": resized, "values_size": values_size}


def registration_fits(data, offset):
    c = Cursor(data)
    count, = c.words()
    fits = set()
    for _ in range(count):
        c.words(2)
        c.table(4)
        n, = c.words()
        for _ in range(n):
            rows = c.table(5)
            size, _ = c.words(2)
            if any(r[2] == ANCHOR_HASH for r in rows):
                fits.add(offset + 4 <= size)
        c.table(7)
        techniques, = c.words()
        c.take(17 * techniques + 8)
    need(len(fits) == 1, "material buffers disagree on free space")
    return fits.pop()


def noop_check(data, oodle):
    """The material and shader codecs must reproduce the stock bytes before anything is edited."""
    mo, ms, so, ss, tail = envelope(data)
    template(data[mo:mo + ms], False)
    if so == 0xFFFFFFFF:
        return
    shader, start, group_size, device, device_size, default_at, programs = shader_layout(data, oodle)
    defaults(shader[default_at:])
    rebuilt, previous = [], device
    for frame in programs:
        rebuilt.append(shader[previous:frame["end"]])
        previous = frame["end"]
    rebuilt.append(shader[previous:device + device_size])
    need(b"".join(rebuilt) == shader[device:device + device_size], "shader device no-op")


def reparent(data, parent):
    """Shaderless child pointing at `parent` (material block offset 4)."""
    mo, ms, so, ss, tail = envelope(data)
    need(so == 0xFFFFFFFF and tail == 0xFFFFFFFF and mo + ms == len(data), "child material layout changed")
    result = bytearray(data)
    struct.pack_into("<Q", result, mo + 4, parent)
    return bytes(result)


def add_child_export(data):
    mo, ms, so, ss, tail = envelope(data)
    need(so == 0xFFFFFFFF and tail == 0xFFFFFFFF and mo + ms == len(data), "child material layout changed")
    material, _, _ = template(data[mo:], True)
    outer = bytearray(data[:mo])
    struct.pack_into("<I", outer, 8, len(material))
    return bytes(outer) + material


def set_hue(data, hue, gpu_default):
    """Write hue/360 into a material's template value (and its last GPU default for the rim)."""
    mo, ms, so, ss, tail = envelope(data)
    c = Cursor(data[mo:mo + ms])
    c.take(20)
    for width in (1, 3, 2):
        c.table(width)
    rows = c.table(5)
    size, = c.words()
    hits = [row for row in rows if row[2] == HASH32]
    need(len(hits) == 1 and hits[0][:2] == (0, 0) and hits[0][4] == 4 and hits[0][3] + 4 <= size,
         "hue reflection row")
    value = struct.pack("<f", hue / 360)
    result = bytearray(data)
    at = mo + c.pos + hits[0][3]
    need(data[at:at + 4] == bytes(4), "hue template default is not zero")
    result[at:at + 4] = value
    if gpu_default:
        shader = data[so:so + ss]
        start, = struct.unpack_from("<I", shader, 20)
        rows = defaults(shader[start:])
        need(rows[-1] == (HASH32, bytes(4)), "hue GPU default is not the last zero entry")
        at = so + start + len(encode_defaults(rows)) - 4
        result[at:at + 4] = value
    else:
        need(so == 0xFFFFFFFF, "expected a shaderless child")
    return bytes(result)


# ---- Pixel programs ----

STORE = re.compile(r"call void @dx\.op\.storeOutput\.f32\(i32 5, i32 0, i32 0, i8 ([0-3]), float ([^)]+)\)")


def f32(value):
    return "0x" + struct.pack(">d", struct.unpack("<f", struct.pack("<f", value))[0]).hex().upper()


def ps_body(text):
    match = re.search(r"^define void @ps_main\(\) \{\n.*?^\}", text, re.M | re.S)
    need(match, "pixel function definition")
    return match


def typed_module(original, stat):
    """The program as assemblable IR: the STAT chunk's typed module with the executable body."""
    executable = ps_body(original)[0]
    module = stat[stat.index("target datalayout"):]
    need(module.count("declare void @ps_main()") == 1 and module.count("!2 = !{i32 0, i32 0}") == 1,
         "STAT entry point or validator profile")
    module = module.replace("!2 = !{i32 0, i32 0}", "!2 = !{i32 1, i32 7}")
    counters = re.search(r"^!dx.counters = !\{(!\d+)\}$", module, re.M)
    need(counters, "STAT counters profile")
    module = re.sub(r"^!dx.counters = .*\n", "", module, flags=re.M)
    module = re.sub(r"^" + re.escape(counters[1]) + r" = .*\n", "", module, flags=re.M)
    definitions = dict(re.findall(r"^!(\d+) = (.*)$", original, re.M))
    references = set(re.findall(r"!(\d+)", executable))
    pending = list(references)
    while pending:
        definition = definitions.get(pending.pop())
        need(definition is not None and len(references) <= 64, "unsupported executable metadata")
        for dependency in re.findall(r"!(\d+)", definition):
            if dependency not in references:
                references.add(dependency)
                pending.append(dependency)
    next_id = 1 + max(map(int, re.findall(r"^!(\d+) =", module, re.M)))
    hints = {number: str(next_id + i) for i, number in enumerate(sorted(references, key=int))}
    for number, substitute in hints.items():
        value = re.sub(r"!(\d+)", lambda m: "!" + hints[m[1]], definitions[number])
        module += f"\n!{substitute} = {value}\n"
    executable = re.sub(r"!(\d+)", lambda m: "!" + hints[m[1]], executable)
    return module.replace("declare void @ps_main()", executable)


def add_export(module, original):
    """Append a float `rainbow_barrels_hue` to c_material_exports; returns (module, offset, handle)."""
    reflected = re.search(r";\s*\}\s*c_material_exports;\s*; Offset:\s*0 Size:\s*(\d+)", original)
    binding = re.search(r"; c_material_exports\s+cbuffer\s+NA\s+NA\s+CB\d+\s+cb(\d+)\s+1", original)
    need(reflected and binding, "material buffer reflection or binding")
    length, register = int(reflected[1]), int(binding[1])
    need(length % 4 == 0 and length >= 4, "material buffer alignment")
    definition = re.search(r"^%c_material_exports = type \{(.*)\}$", module, re.M)
    resource = re.search(r'(%c_material_exports\* undef, !"c_material_exports", i32 0, i32 '
                         + str(register) + r', i32 1, i32 )' + str(length) + r'(, null)', module)
    annotation = re.search(r"%c_material_exports undef, (!\d+)", module)
    need(definition and resource and annotation, "typed material-buffer profile")
    new_id = 1 + max(map(int, re.findall(r"^!(\d+) =", module, re.M)))
    module = module.replace(definition[0], definition[0][:-2] + ", float }")
    module = module.replace(resource[0], resource[1] + str(length + 4) + resource[2])
    row = re.search(r"^" + re.escape(annotation[1]) + r" = !\{i32 " + str(length) + r", (.*)\}$", module, re.M)
    need(row, "material field annotations")
    module = module.replace(row[0], f"{annotation[1]} = !{{i32 {length + 4}, {row[1]}, !{new_id}}}")
    module += f'\n!{new_id} = !{{i32 6, !"{EXPORT_NAME}", i32 3, i32 {length}, i32 7, i32 9}}\n'
    handles = re.findall(r"^  (%[\w.]+) = call %dx.types.Handle @dx.op.createHandle\(i32 57, i8 2, i32 "
                         + str(register) + r", i32 " + str(register) + r", i1 false\)", ps_body(original)[0], re.M)
    need(len(handles) == 1, "unique material cbuffer handle")
    return module, length, handles[0]


def hue_output(module, offset, handle):
    """Final RGB -> max(r, g, b) times the hue wheel colour read from the material buffer."""
    match = ps_body(module)
    function = match[0]
    stores = STORE.findall(function)
    need(len(stores) == 4 and sorted(ch for ch, _ in stores) == list("0123"), "single RGBA target output")
    sources = {int(ch): value for ch, value in stores}
    need(all(re.fullmatch(r"%[\w.]+", sources[i]) for i in range(3)), "colour output is not an SSA value")
    anchor = re.search(r"^  call void @dx.op.storeOutput.f32\(i32 5, i32 0, i32 0, i8 0, float "
                       + re.escape(sources[0]) + r"\).*$", function, re.M)
    need(anchor, "RGB output anchor")
    register, component = divmod(offset, 16)
    code = [
        f"  %rb.control = call %dx.types.CBufRet.f32 @dx.op.cbufferLoadLegacy.f32(i32 59, %dx.types.Handle {handle}, i32 {register})",
        f"  %rb.hue = extractvalue %dx.types.CBufRet.f32 %rb.control, {component // 4}",
        f"  %rb.maxrg = call float @dx.op.binary.f32(i32 35, float {sources[0]}, float {sources[1]})",
        f"  %rb.value = call float @dx.op.binary.f32(i32 35, float %rb.maxrg, float {sources[2]})",
    ]
    for color, turn in (("r", 0.0), ("g", 2 / 3), ("b", 1 / 3)):
        p = "%rb." + color
        code += [
            f"  {p}.shift = fadd float %rb.hue, {f32(turn)}",
            f"  {p}.phase = call float @dx.op.unary.f32(i32 22, float {p}.shift)",
            f"  {p}.six = fmul float {p}.phase, 6.000000e+00",
            f"  {p}.center = fsub float {p}.six, 3.000000e+00",
            f"  {p}.abs = call float @dx.op.unary.f32(i32 6, float {p}.center)",
            f"  {p}.minus = fsub float {p}.abs, 1.000000e+00",
            f"  {p}.unit = call float @dx.op.unary.f32(i32 7, float {p}.minus)",
            f"  %rb.{color} = fmul float {p}.unit, %rb.value",
        ]
    altered = function[:anchor.start()] + "\n".join(code) + "\n" + function[anchor.start():]
    for channel, color in enumerate("rgb"):
        line = re.search(r"^  call void @dx.op.storeOutput.f32\(i32 5, i32 0, i32 0, i8 "
                         + str(channel) + r", float " + re.escape(sources[channel]) + r"\).*$", altered, re.M)
        need(line, "distinct RGB store")
        replacement = line[0].replace("float " + sources[channel] + ")", "float %rb." + color + ")")
        altered = altered[:line.start()] + replacement + altered[line.end():]
    module = module[:match.start()] + altered + module[match.end():]
    for name, declaration in (("unary", "declare float @dx.op.unary.f32(i32, float) #0"),
                              ("binary", "declare float @dx.op.binary.f32(i32, float, float) #0")):
        if "declare float @dx.op." + name + ".f32(" not in module:
            module += "\n" + declaration + "\n"
    return module


def body_lines(text):
    # typed_module renumbers metadata nodes; their references are not program behaviour.
    return [re.sub(r"!\d+", "!N", line) for line in ps_body(text)[0].split("\n")]


class Programs:
    """Hue-authors each distinct colour-writing pixel program once; caches by stock SHA-256."""

    def __init__(self, dxc):
        self.dxc, self.cache = dxc, {}

    def author(self, program):
        digest = sha(program)
        if digest not in self.cache:
            self.cache[digest] = self._author(program)
        return self.cache[digest]

    def _author(self, program):
        """None for a pixel program without a colour target; else (offset, DXBC, report)."""
        original = self.dxc.dump(program)
        if not STORE.findall(ps_body(original)[0]):
            return None
        parts = dxbc_parts(program)
        need(all(k in parts for k in ("STAT", "DXIL", "SFI0", "ISG1", "OSG1", "PSV0")), "program chunks changed")
        noop = typed_module(original, self.dxc.dump(parts["STAT"]))
        module, offset, handle = add_export(noop, original)
        authored = hue_output(module, offset, handle)
        built = {}
        for kind, text in (("noop", noop), ("hue", authored)):
            signed = self.dxc.compile(text)
            candidate = dxbc_parts(signed)
            need(all(parts[k] == candidate[k] for k in ("SFI0", "ISG1", "OSG1", "PSV0")), "program signature changed")
            built[kind] = signed
        # The no-op rebuild must disassemble to the stock function; the edit only adds the hue.
        need(body_lines(original) == body_lines(self.dxc.dump(built["noop"])),
             "no-op rebuild does not reproduce the stock function")
        readback = self.dxc.dump(built["hue"])
        need(len(re.findall(r";\s+float rainbow_barrels_hue;\s*; Offset:\s*" + str(offset) + r"\s*$",
                            readback, re.M)) == 1, "hue reflection missing after readback")
        need(sum("%rb." in line for line in body_lines(readback)) >= 3, "hue transform missing after readback")
        return offset, built["hue"], {"stock_sha256": sha(program), "export_offset": offset,
                                      "noop_sha256": sha(built["noop"]), "hue_sha256": sha(built["hue"])}


def hue_material(data, programs, oodle):
    """A shader-bearing material with the hue scalar and every colour-writing pixel program."""
    noop_check(data, oodle)
    stock = shader_layout(data, oodle)[6]
    replacements, offsets, rows = {}, set(), []
    for frame in stock:
        if frame["stage"] != 0 or frame["sha256"] in replacements:
            continue
        result = programs.author(frame["program"])
        if result is None:
            continue
        offset, compiled, row = result
        replacements[frame["sha256"]] = compiled
        offsets.add(offset)
        rows.append(row)
    need(len(offsets) == 1, f"colour programs disagree on the material buffer size: {sorted(offsets)}")
    offset = offsets.pop()
    result, report = author_shader_material(data, replacements, offset, oodle)
    readback = shader_layout(result, oodle)[6]
    need(len(readback) == len(stock), "program count changed")
    for old, new in zip(stock, readback):
        want = sha(replacements[old["sha256"]]) if old["sha256"] in replacements else old["sha256"]
        need(new["sha256"] == want, "program read back wrong")
    return result, report | {"export_offset": offset, "hue_programs": rows}


# ---- The two bundles ----

def graph(records, effects, stock_root):
    """Materials of the effects' billboard clouds: {id: (stock path, bytes, parent or None)}."""
    found = {}
    for effect in effects:
        for row in profile(find(records, PARTICLES, murmur64(effect))):
            if row["type"] == 0 and row["material"]:
                found.setdefault(row["material"], None)
    result = {}
    pending = list(found)
    while pending:
        name = pending.pop()
        path, data = material_stream(records, name, stock_root)
        mo, ms, so, ss, tail = envelope(data)
        parent = None
        if so == 0xFFFFFFFF:
            parent, = struct.unpack_from("<Q", data, mo + 4)
            need(parent, f"shaderless material {name:016x} has no parent")
            if parent not in result and parent not in pending:
                pending.append(parent)
        result[name] = (path, data, parent)
    for name, (_, _, parent) in result.items():
        need(parent is None or result[parent][2] is None, "material grandparent")
    return result


def stock_bundle(path, oodle):
    data = path.read_bytes()
    opaque, records = read_bundle(data, oodle)
    noop = write_bundle(opaque, records)
    need(read_bundle(noop, oodle) == (opaque, records), "stored bundle no-op roundtrip")
    return data, opaque, records


EXPLOSIONS = (("content/fx/particles/explosions/frag_grenade_01", "explosive"),
              ("content/fx/particles/destructibles/explosive_barrel_explosion", "fire"))
LIQUID = (("content/fx/particles/liquid_area/fire_lingering", "fire_lingering_filled", "ground_filled"),
          ("content/fx/particles/liquid_area/fire_lingering_edge", "fire_lingering_rim", "ground_edge"))


def explosion(stock_root, oodle, programs, log):
    data, opaque, records = stock_bundle(stock_root / EXPLOSION, oodle)
    materials = graph(records, [e for e, _ in EXPLOSIONS], stock_root)
    streams, report, keys = {}, [], {}
    for name in materials:
        keys[name] = murmur64(f"{CUSTOM}{name:016x}")
    for name in sorted(materials, key=lambda n: f"{n:016x}"):
        path, source, parent = materials[name]
        noop_check(source, oodle)
        if parent is None:
            result, row = hue_material(source, programs, oodle)
        else:
            result, row = reparent(source, keys[parent]), {"parent": f"{parent:016x}"}
        streams[keys[name]] = result
        report.append({"material": f"{name:016x}", "stock": path, "stock_sha256": sha(source),
                       "output_sha256": sha(result)} | row)
        log(f"  material {name:016x}: {'child of ' + row['parent'] if parent else 'hue shader'}")
    out = list(records)
    occupied = {row[:2] for row, _ in records}
    for key in streams:
        out.append(((MATERIAL, key, 4), streamed_record(MATERIAL, key, f"data/rb/{key:016x}".encode() + bytes(4))))
    for effect, label in EXPLOSIONS:
        source = find(records, PARTICLES, murmur64(effect))
        lights = light_graphs(source)
        for hue in HUES:
            name = f"content/fx/particles/rainbow_barrels/{label}_hue_{hue:03d}"
            raw = clone_particle(recolor_lights(source, lights, hue), effect, name, label,
                                 {m: keys[m] for m in materials})
            out.append(((PARTICLES, murmur64(name), 0), raw))
        report.append({"particle": effect, "light_clouds": lights})
    need(len({row[:2] for row, _ in out}) == len(out) and occupied <= {row[:2] for row, _ in out},
         "explosion identity collision")
    return data, write_bundle(opaque, out), streams, report


def ground(stock_root, oodle, programs, log):
    data, opaque, records = stock_bundle(stock_root / GROUND, oodle)
    materials = graph(records, [e for e, _, _ in LIQUID], stock_root)
    keys = {name: murmur64(f"{CUSTOM}liquid_{name:016x}") for name in materials}
    streams, report, base = {}, [], {}
    for name in sorted(materials, key=lambda n: f"{n:016x}"):
        path, source, parent = materials[name]
        noop_check(source, oodle)
        if parent is None:
            result, row = hue_material(source, programs, oodle)
        else:
            result, row = add_child_export(reparent(source, keys[parent])), {"parent": f"{parent:016x}"}
        base[name] = result
        streams[keys[name]] = result
        report.append({"material": f"{name:016x}", "stock": path, "stock_sha256": sha(source),
                       "output_sha256": sha(result)} | row)
        log(f"  material {name:016x}: {'child of ' + row['parent'] if parent else 'hue shader'}")
    out = list(records)
    for key in streams:
        out.append(((MATERIAL, key, 4), streamed_record(MATERIAL, key, f"data/rb/{key:016x}".encode() + bytes(4))))
    clones = {}
    for effect, custom, clouds in LIQUID:
        source = find(records, PARTICLES, murmur64(effect))
        raw = clone_particle(source, effect, "content/fx/particles/rainbow_barrels/" + custom, clouds, keys)
        out.append(((PARTICLES, murmur64("content/fx/particles/rainbow_barrels/" + custom), 0), raw))
        bound = {row["material"] for row in profile(source) if row["type"] == 0 and row["material"]}
        clones[custom] = (raw, bound)
    # Per hue: the billboard materials the two clones bind (children and the rim's shader).
    variable = sorted(set().union(*(bound for _, bound in clones.values())), key=lambda n: f"{n:016x}")
    floor = floor_graph(clones["fire_lingering_filled"][0])
    for hue in HUES:
        hued = {}
        for name in variable:
            path = f"{CUSTOM}liquid_{name:016x}_hue_{hue:03d}"
            key = murmur64(path)
            streams[key] = set_hue(base[name], hue, materials[name][2] is None)
            hued[keys[name]] = key
            out.append(((MATERIAL, key, 4), streamed_record(MATERIAL, key, f"data/rb/{key:016x}".encode() + bytes(4))))
        for _, custom, _ in LIQUID:
            raw, _ = clones[custom]
            name = f"content/fx/particles/rainbow_barrels/{custom}_hue_{hue:03d}"
            variant = bytearray(raw)
            struct.pack_into("<Q", variant, 8, murmur64(name))
            for row in profile(raw):
                if row["type"] == 0 and row["material"]:
                    struct.pack_into("<Q", variant, row["visualizer"] + 12, hued[row["material"]])
            if custom == "fire_lingering_filled":
                for offset, intensity in floor:
                    struct.pack_into("<3f", variant, offset, *(intensity * c for c in rgb(hue)))
            out.append(((PARTICLES, murmur64(name), 0), bytes(variant)))
    report.append({"hue_materials": [f"{n:016x}" for n in variable], "floor_rgb_offsets": [o for o, _ in floor]})
    need(len({row[:2] for row, _ in out}) == len(out), "ground identity collision")
    return data, write_bundle(opaque, out), streams, report


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game", type=Path, default=GAME)
    parser.add_argument("--stock", type=Path, help="folder laid out like the game (bundle/<name>, "
                        "bundle/data/..) instead of the game folder; nothing is pinned")
    parser.add_argument("--out", type=Path, help="write the payload here instead of the mod; nothing is pinned")
    args = parser.parse_args()
    stock_root = args.stock or args.game
    oodle = bundle8.Oodle(args.game / "binaries/oo2core_9_win64.dll")
    dxc = Dxc()
    programs = Programs(dxc)
    config = json.loads((MOD / "reforge.json").read_text(encoding="utf-8"))
    redirects = {r["stock"]: r for r in config["redirects"]}
    need(set(redirects) == {EXPLOSION, GROUND} and [d["stock"] for d in config["virtual_dirs"]] == ["bundle/data/rb"],
         "reforge.json redirects differ from this script")
    materials_dir = config["virtual_dirs"][0]["dir"]
    bundles, streams, reports = {}, {}, {}
    for target, build in ((EXPLOSION, explosion), (GROUND, ground)):
        print(f"{target}:")
        stock, stored, made, report = build(stock_root, oodle, programs, print)
        packed = bundle8.pack(stored, oodle)
        need(not set(made) & set(streams), "material stream name collision")
        streams.update(made)
        bundles[target] = (stock, packed)
        reports[target] = {"stock_sha256": sha(stock), "stored_sha256": sha(stored), "output_sha256": sha(packed),
                           "output_bytes": len(packed), "streams": len(made), "details": report}
        print(f"  stock {sha(stock)[:12]} -> stored {sha(stored)[:12]} -> packed {sha(packed)[:12]}, "
              f"{len(made)} material streams")
    need(len(streams) == 1098, f"expected 1,098 material streams, built {len(streams)}")
    out = args.out or MOD
    for target, (_, packed) in bundles.items():
        path = out / redirects[target]["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(packed)
    folder = out / materials_dir
    folder.mkdir(parents=True, exist_ok=True)
    names = {f"{key:016x}" for key in streams}
    stale = [p for p in folder.iterdir() if p.name not in names]
    for key, data in streams.items():
        (folder / f"{key:016x}").write_bytes(data)
    for path in stale:
        path.unlink()
    summary = {"dxc": dxc.version, "game": str(args.game), "stock_folder": str(args.stock) if args.stock else None,
               "programs": [row for row in (v[2] for v in programs.cache.values() if v)], "bundles": reports,
               "streams_sha256": sha(b"".join(bytes.fromhex(n) + bytes.fromhex(sha(streams[int(n, 16)]))
                                              for n in sorted(names)))}
    inputs = [r["stock_sha256"] for r in reports.values()]
    inputs += [d["stock_sha256"] for r in reports.values() for d in r["details"] if "stock_sha256" in d]
    report_dir = MOD / "analysis" / ("rebuild-" + sha("".join(inputs).encode())[:12])
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"{len(streams)} material streams, {len(stale)} stale removed; report: {report_dir / 'report.json'}")
    if args.stock or args.out:
        print(f"payload written to {out}; reforge.json not changed")
        return
    for target, (stock, _) in bundles.items():
        redirects[target]["sha256"] = sha(stock)
    config["redirects"].sort(key=lambda r: r["stock"])
    (MOD / "reforge.json").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                                      encoding="utf-8", newline="\n")
    print("pinned the stock bundle hashes in reforge.json (late_load kept); now run `reforge build`")


if __name__ == "__main__":
    try:
        main()
    except Fail as exc:
        sys.exit(f"rebuild_payload: {exc}")
