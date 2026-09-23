"""Read the stock frame metadata around one barrel material buffer binding."""

import json
import struct

from probe_layout import PATH
from profile_exports import Cursor
from profile_shaders import inventory


WIDTHS = (6, 0, 0, 7, 7, 7, 7, 4, 3, 3)


def main():
    data = PATH.read_bytes()
    _, _, _, so, ss, _, _ = struct.unpack_from("<7I", data)
    shader = data[so:so + ss]
    results = []
    for row in inventory(data):
        begin = row["offset"]
        envelope, size = struct.unpack_from("<II", shader, begin - 8)
        if envelope != 1:
            raise ValueError("Shader frame envelope")
        c = Cursor(shader)
        c.pos = begin + size
        header = c.words(4)
        if header[0] != 5:
            raise ValueError("Frame metadata kind")
        tables = []
        for width in WIDTHS:
            rows = c.table(width)
            tables.append(rows)
        results.append({"program_offset": begin, "stage": row["stage"],
                        "metadata_header": header, "metadata_size": c.pos - begin - size,
                        "table_counts": [len(rows) for rows in tables],
                        "material_buffer_rows": [r for r in tables[0]
                                                 if 52 in r or 64 in r or 56 in r]})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
