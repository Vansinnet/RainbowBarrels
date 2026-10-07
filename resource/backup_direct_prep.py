"""Back up the tracked RainbowBarrels tree before the direct-release cleanup."""

import hashlib
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


mod = Path(__file__).resolve().parents[1]
workspace = mod.parents[2]
backup = workspace / "backups" / f"RainbowBarrels-direct-release-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
if not backup.parent.is_dir():
    raise RuntimeError(f"Expected backup parent missing: {backup.parent}")
tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=mod).decode("utf-8").strip("\0").split("\0")
lines = []
for relative in tracked:
    source = mod / relative
    if not source.is_file():
        raise RuntimeError(f"Missing tracked file: {source}")
    destination = backup / "files" / "mods" / "active" / mod.name / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    lines.append(f"{digest}  files/mods/active/{mod.name}/{relative}")
(backup / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")
(backup / "ROLLBACK.txt").write_text(
    "Paths under files/ are relative to the workspace root. Verify SHA256SUMS before restoring individual files.\n"
    "The prior tracked sources also remain at Git commit f414a6d. No installed game files were changed.\n",
    encoding="utf-8",
)
print(f"Backup: {backup} ({len(lines)} files), SHA256SUMS and ROLLBACK.txt written")
