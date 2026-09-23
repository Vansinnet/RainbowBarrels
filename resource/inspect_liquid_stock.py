"""Index-only lookup for the two source-named prop-fire particle resources."""

import json

from inspect_stock import inspect, locate


LIQUID_EFFECTS = (
    "content/fx/particles/liquid_area/fire_lingering",
    "content/fx/particles/liquid_area/fire_lingering_edge",
)


if __name__ == "__main__":
    print(json.dumps({"standalone": [inspect(name) for name in LIQUID_EFFECTS],
                      "indexed": locate(LIQUID_EFFECTS)}, indent=2))
