"""Exact read-only roundtrip of one barrel material export/group profile."""

import hashlib
import json
from pathlib import Path
import struct

from probe_layout import PATH, PROVENANCE


class Cursor:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, size):
        if not 0 <= size <= len(self.data) - self.pos:
            raise ValueError("Section boundary")
        start = self.pos
        self.pos += size
        return self.data[start:self.pos]

    def words(self, count=1):
        return struct.unpack("<" + "I" * count, self.take(4 * count))

    def table(self, width):
        count, = self.words()
        if count > 4096:
            raise ValueError("Table count")
        return [self.words(width) for _ in range(count)]


def pack_words(values):
    return struct.pack("<" + "I" * len(values), *values)


def pack_table(rows):
    return pack_words((len(rows),)) + b"".join(pack_words(row) for row in rows)


def template(data):
    c = Cursor(data)
    head = c.take(20)
    rows = [c.table(width) for width in (1, 3, 2, 5)]
    values = c.take(c.words()[0])
    trailing = c.take(c.words()[0] * 5)
    last = c.table(2)
    if c.pos != len(data):
        raise ValueError("Material template exhaustion")
    rebuilt = (head + b"".join(pack_table(row) for row in rows)
               + pack_words((len(values),)) + values
               + pack_words((len(trailing) // 5,)) + trailing + pack_table(last))
    if rebuilt != data:
        raise ValueError("Material identity reconstruction")
    return {"reflection": rows[3], "values_size": len(values)}


def groups(data):
    c = Cursor(data)
    count, = c.words()
    if not 1 <= count <= 32:
        raise ValueError("Shader groups count")
    report = []
    rebuilt = pack_words((count,))
    for _ in range(count):
        key, allocation = c.words(2)
        resources = c.table(4)
        buffers_count, = c.words()
        if not 1 <= buffers_count <= 16:
            raise ValueError("Material buffer count")
        part = pack_words((key, allocation)) + pack_table(resources) + pack_words((buffers_count,))
        buffers = []
        for _ in range(buffers_count):
            descriptors = c.table(5)
            size, offset = c.words(2)
            if not 0 < size <= 65536 or any(row[3] + row[4] * max(1, row[1]) > size for row in descriptors):
                raise ValueError("Descriptor extent")
            buffers.append({"size": size, "offset": offset, "descriptors": len(descriptors)})
            part += pack_table(descriptors) + pack_words((size, offset))
        associations = c.table(7)
        technique_count, = c.words()
        if technique_count > 64:
            raise ValueError("Technique count")
        opaque = c.take(17 * technique_count)
        trailer = c.take(8)
        part += pack_table(associations) + pack_words((technique_count,)) + opaque + trailer
        rebuilt += part
        report.append({"key": key, "allocation": allocation, "resources": len(resources),
                       "buffers": buffers, "associations": len(associations),
                       "techniques": technique_count, "trailer": trailer.hex()})
    if c.pos != len(data) or rebuilt != data:
        raise ValueError("Shader groups exhaustion/roundtrip")
    return report


def main():
    entry = next(row for row in json.loads(PROVENANCE.read_text())["materials"]
                 if row["identity"] == PATH.stem)
    data = PATH.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["source_sha256"]:
        raise ValueError("Stock material identity")
    version, mo, ms, so, ss, tail, ts = struct.unpack_from("<7I", data)
    if version != 61 or mo != 28 or so != mo + ms or so + ss > len(data):
        raise ValueError("Material sections")
    material = template(data[mo:so])
    shader = data[so:so + ss]
    fields = struct.unpack_from("<12I", shader)
    start, length = fields[8:10]
    if fields[0] != 43 or not 48 <= start < start + length <= fields[10] <= len(shader):
        raise ValueError("Shader sections")
    report = {"material": material, "shader_groups": groups(shader[start:start + length]),
              "material_size": ms, "shader_size": ss}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
