"""Verify the target material shader's default-value table roundtrip."""

import json
import struct

from probe_layout import PATH
from profile_exports import Cursor, pack_table, pack_words


def defaults(data):
    c = Cursor(data)
    if c.words() != (0,):
        raise ValueError("Shader defaults prefix")
    descriptors = c.table(3)
    results = []
    for key, width, offset in descriptors:
        if width not in (1, 2, 3, 4) or c.pos != offset:
            raise ValueError("Shader default offset")
        results.append((key, c.take(4 * width)))
    if any(data[c.pos:]) or len(data) - c.pos > 15:
        raise ValueError("Shader defaults padding")
    encoded = encode(results)
    if data != encoded + bytes(len(data) - len(encoded)):
        raise ValueError("Shader defaults byte reconstruction")
    return results


def encode(rows):
    descriptors = []
    values = b""
    offset = 8 + len(rows) * 12
    for name, value in rows:
        if len(value) not in (4, 8, 12, 16):
            raise ValueError("Default value width")
        descriptors.append((name, len(value) // 4, offset))
        values += value
        offset += len(value)
    return pack_words((0,)) + pack_table(descriptors) + values


def main():
    data = PATH.read_bytes()
    _, _, _, so, ss, _, _ = struct.unpack_from("<7I", data)
    shader = data[so:so + ss]
    start, = struct.unpack_from("<I", shader, 20)
    rows = defaults(shader[start:])
    print(json.dumps({"count": len(rows),
                      "keys_and_bytes": [(f"{key:08x}", value.hex()) for key, value in rows]}, indent=2))


if __name__ == "__main__":
    main()
