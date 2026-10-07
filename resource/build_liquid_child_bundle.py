"""Build a v2 liquid candidate by replacing only two external child streams."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "analysis/liquid-bundle-trial-24735202"
MATERIALS = ROOT / "analysis/liquid-hue-materials-v2-24735202"
OUT = ROOT / "analysis/liquid-bundle-v2-trial-24735202"
PACKAGE = "b224998193576995"
BASE_BUNDLE_SHA = "6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if OUT.exists():
        raise ValueError("Output already exists")
    report = json.loads((BASE / "report.json").read_text())
    bundle = (BASE / "bundle" / PACKAGE).read_bytes()
    if sha(bundle) != BASE_BUNDLE_SHA or report["candidate_bundle_sha256"] != BASE_BUNDLE_SHA:
        raise ValueError("Installed-base liquid bundle identity changed")
    materials = {row["material"]: row for row in json.loads(
        (MATERIALS / "provenance.json").read_text())["materials"]}
    assets = []
    changed = []
    payloads = {}
    for item in report["added_assets"]:
        row = dict(item)
        if item["kind"] == "material":
            name = item["identity"].rsplit("_", 1)[-1]
            material = materials[name]
            payload = (MATERIALS / (name + ".material")).read_bytes()
            if sha(payload) != material["candidate_sha256"]:
                raise ValueError("V2 material candidate changed: " + name)
            row["sha256"] = sha(payload)
            row["bytes"] = len(payload)
            payloads[item["stream"]] = payload
            if row["sha256"] != item["sha256"]:
                if material["kind"] != "shaderless_child":
                    raise ValueError("Only child streams may differ from v1")
                changed.append({"identity": item["identity"], "stream": item["stream"],
                                "v1_sha256": item["sha256"], "v2_sha256": row["sha256"],
                                "v1_bytes": item["bytes"], "v2_bytes": row["bytes"]})
        assets.append(row)
    if len(payloads) != 5 or len(changed) != 2:
        raise ValueError("Exactly two child streams must change")
    OUT.mkdir(parents=True)
    (OUT / "bundle").mkdir()
    (OUT / "bundle" / PACKAGE).write_bytes(bundle)
    for relative, payload in payloads.items():
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    result = dict(report)
    result["added_assets"] = assets
    result["changed_from_v1"] = changed
    result["status"] = "offline child-export liquid-fire candidate; not installed or game-tested"
    (OUT / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"candidate_bundle_sha256": sha(bundle),
                      "bundle_changed_from_v1": False,
                      "changed_child_streams": changed,
                      "status": result["status"]}, indent=2))


if __name__ == "__main__":
    main()
