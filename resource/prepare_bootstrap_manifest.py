"""Generate the embedded, resource-only bootstrap recipe; never changes legacy inputs."""
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    legacy = json.loads((root / "payload/manifest.json").read_text(encoding="utf-8"))
    assert {r["target"] for r in legacy["bundles"]} == {
        "bundle/98bb14b1d247a0c8", "bundle/b224998193576995"}
    assert len(legacy["streams"]) == 1098
    rows = []
    for b in legacy["bundles"]:
        rows.append(dict(target=b["target"], payload="payload/bundles/" + b["target"].split("/")[-1],
                         size=b["outputSize"], sha256=b["outputSha256"],
                         stockSize=b["stockSize"], stockSha256=b["stockSha256"]))
    for s in legacy["streams"]:
        name = s["target"].removeprefix("bundle/data/rb/")
        assert len(name) == 16 and all(c in "0123456789abcdef" for c in name)
        assert s["payload"] == "payload/materials/" + name
        rows.append(dict(target=s["target"], payload=s["payload"], size=s["size"],
                         sha256=s["sha256"], stockSize=0, stockSha256=None))
    assert len({r["target"] for r in rows}) == 1100
    for row in rows:
        path = root / row["payload"]
        assert not path.is_symlink()
        assert path.stat().st_size == row["size"], str(path)
        assert hashlib.file_digest(path.open("rb"), "sha256").hexdigest() == row["sha256"], str(path)
    result = dict(version="1.1.0", steamAppId=legacy["steamAppId"], steamBuild=legacy["steamBuild"],
                  exeVersion=legacy["exeVersion"], files=rows)
    output = root / "bootstrap/RainbowBarrels.Setup/manifest.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(rows)} payloads; generated {output}")


if __name__ == "__main__":
    main()
