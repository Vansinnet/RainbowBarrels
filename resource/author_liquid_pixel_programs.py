"""Author and DXC-validate six source-pinned liquid-fire hue pixel programs."""

from pathlib import Path

from author_pixel_programs import ROOT, build


if __name__ == "__main__":
    build(sources=("liquid-shaders-24735202",),
          output=ROOT / "analysis/liquid-hue-programs-24735202", expected_count=6)
