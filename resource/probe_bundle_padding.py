"""Inspect only the decoded final chunk padding of the target stock package."""

import hashlib
import json

from analyze_effects import GAME, SOURCES, decode_bundle_parts, decoder
from profile_particles import HERE


def main():
    source = GAME / SOURCES[1][0]
    data = source.read_bytes()
    evidence = json.loads((HERE / "provenance.json").read_text())["particles"]
    expected = next(item["source_sha256"] for item in evidence if item["game_source"] == str(source))
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Stock source drift")
    records, padding = decode_bundle_parts(data, decoder())
    print(json.dumps({"source_bundle": str(source), "resources": len(records),
                      "decoded_padding_length": len(padding),
                      "decoded_padding_sha256": hashlib.sha256(padding).hexdigest(),
                      "decoded_padding_nonzero": sum(bool(byte) for byte in padding)}, indent=2))


if __name__ == "__main__":
    main()
