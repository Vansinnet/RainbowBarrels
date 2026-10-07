"""Read-only, SHA-pinned decoder check on the untouched frag-grenade stock bundle."""

import hashlib

from analyze_effects import GAME, decode_bundle_parts, decoder


SOURCE = GAME / "bundle/d2b0b18252164f5b"
SOURCE_SHA = "86d24e1dd5796d4cbc2dee764b1860b2b327c21dfbad5e4f45083d1c9c045fa9"


def main():
    data = SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA:
        raise ValueError("Stock decoder control changed or became a mod replacement")
    records, _ = decode_bundle_parts(data, decoder())
    body = b"".join(record for _, record, _ in records)
    print({"source_sha256": SOURCE_SHA, "count": len(records),
           "stock_logical_sha256": hashlib.sha256(body).hexdigest(),
           "logical_bytes": len(body)})


if __name__ == "__main__":
    main()
