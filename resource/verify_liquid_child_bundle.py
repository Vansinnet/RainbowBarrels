"""Independent readback of the two child-export stream changes in liquid v2."""

import hashlib
import json
from pathlib import Path
import struct

from author_material import HASH32
from author_material_families import material_template
from inspect_stock import murmur64
from profile_exports import template


ROOT = Path(__file__).resolve().parents[1] / "analysis"
STOCK = ROOT / "liquid-stock-24735202"
V1 = ROOT / "liquid-bundle-trial-24735202"
V2 = ROOT / "liquid-bundle-v2-trial-24735202"
PACKAGE = "b224998193576995"
CHILDREN = {"d11c8f091a39ef54": "1cc58f33452ca960",
            "62b838cfa247b2ca": "62c7bb3aa1cac9c2"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def envelope(data):
    fields = struct.unpack_from("<7I", data)
    version, material_offset, material_size, shader_offset, shader_size, tail_offset, tail_size = fields
    if (version != 61 or material_offset != 28 or material_offset + material_size != len(data)
            or shader_offset != 0xFFFFFFFF or shader_size != 0
            or tail_offset != 0xFFFFFFFF or tail_size != 0):
        raise ValueError("Shaderless child envelope")
    return data[material_offset:]


def main():
    v1_report = json.loads((V1 / "report.json").read_text())
    v2_report = json.loads((V2 / "report.json").read_text())
    v1_bundle = (V1 / "bundle" / PACKAGE).read_bytes()
    v2_bundle = (V2 / "bundle" / PACKAGE).read_bytes()
    if v2_bundle != v1_bundle or sha(v2_bundle) != v2_report["candidate_bundle_sha256"]:
        raise ValueError("V2 must preserve the accepted logical-resource bundle")
    stocks = {row["identity"]: row for row in json.loads(
        (STOCK / "materials-provenance.json").read_text())["materials"]}
    v1_assets = {row["identity"]: row for row in v1_report["added_assets"]}
    v2_assets = {row["identity"]: row for row in v2_report["added_assets"]}
    verified = []
    for name, parent in CHILDREN.items():
        identity = "content/fx/materials/rainbow_barrels/liquid_" + name
        old_item, new_item = v1_assets[identity], v2_assets[identity]
        stock_row = stocks[name]
        stock = (STOCK / "materials" / stock_row["retained_file"]).read_bytes()
        before = (V1 / old_item["stream"]).read_bytes()
        after = (V2 / new_item["stream"]).read_bytes()
        if (sha(stock) != stock_row["stream_sha256"] or sha(before) != old_item["sha256"]
                or sha(after) != new_item["sha256"]):
            raise ValueError("Child stream provenance: " + name)
        stock_material, old_material, new_material = map(envelope, (stock, before, after))
        custom_parent = murmur64("content/fx/materials/rainbow_barrels/liquid_" + parent)
        if (struct.unpack_from("<Q", stock_material, 4)[0] != int(parent, 16)
                or struct.unpack_from("<Q", old_material, 4)[0] != custom_parent
                or struct.unpack_from("<Q", new_material, 4)[0] != custom_parent):
            raise ValueError("Child parent chain: " + name)
        old_restore = bytearray(old_material)
        struct.pack_into("<Q", old_restore, 4, int(parent, 16))
        if bytes(old_restore) != stock_material:
            raise ValueError("V1 child had more than the parent redirect: " + name)
        old_profile, new_profile = template(old_material), template(new_material)
        if (new_profile["reflection"][:-1] != old_profile["reflection"]
                or new_profile["reflection"][-1] != (0, 0, HASH32, old_profile["values_size"], 4)
                or new_profile["values_size"] != old_profile["values_size"] + 4
                or new_material != material_template(old_material, True)):
            raise ValueError("Child scalar export delta: " + name)
        if len(after) != len(before) + 24:
            raise ValueError("Child payload growth: " + name)
        verified.append({"material": name, "parent": parent,
                         "export_offset": old_profile["values_size"],
                         "v1_sha256": sha(before), "v2_sha256": sha(after)})
    for identity, old_item in v1_assets.items():
        new_item = v2_assets[identity]
        if identity.rsplit("_", 1)[-1] in CHILDREN:
            continue
        if old_item != new_item:
            raise ValueError("Unrelated v2 asset metadata changed: " + identity)
        if old_item["kind"] == "material" and (V1 / old_item["stream"]).read_bytes() != (V2 / new_item["stream"]).read_bytes():
            raise ValueError("Unrelated material stream changed: " + identity)
    if len(verified) != 2 or len(v2_report["changed_from_v1"]) != 2:
        raise ValueError("Both and only child streams required")
    print(json.dumps({"bundle_sha256": sha(v2_bundle), "bundle_changed_from_v1": False,
                      "verified_child_exports": verified,
                      "status": "offline structural readback; engine acceptance remains runtime pending"}, indent=2))


if __name__ == "__main__":
    main()
