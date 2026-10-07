"""Check the first hue-shader candidate without altering retained evidence."""

import hashlib
import json
import re

from experiment_hue import OUT, SOURCE, chunks


def main():
    original = chunks(SOURCE.read_bytes())
    candidate = chunks((OUT / "candidate.dxbc").read_bytes())
    text = (OUT / "candidate.ll.txt").read_text()
    signature = {tag: original[tag] == candidate[tag]
                 for tag in ("SFI0", "ISG1", "OSG1", "PSV0")}
    matches = re.findall(r";\s+float rainbow_barrels_hue;\s*; Offset:\s*52\s*$", text, re.M)
    result = {"export_count": len(matches), "signature_unchanged": signature,
              "candidate_sha256": hashlib.sha256((OUT / "candidate.dxbc").read_bytes()).hexdigest()}
    print(json.dumps(result, indent=2))
    if len(matches) != 1 or not all(signature.values()):
        raise ValueError("Hue shader candidate validation failed")
    report = OUT / "report.json"
    if report.exists():
        raise ValueError("Existing report must not be overwritten")
    report.write_text(json.dumps({"source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                                  **result,
                                  "status": "offline DXC result; material registration untested"},
                                 indent=2) + "\n")


if __name__ == "__main__":
    main()
