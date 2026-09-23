# RainbowBarrels installer source

The Windows x64 .NET 10 desktop installer handles Install, Repair, and Uninstall
for Darktide build `24735202` only. It does not connect to the internet, read
accounts, elevate privileges, or execute scripts. Stock resources are never
included in the release. The installer validates the two pristine stock game
bundles, uses the SHA-pinned Oodle decoder already present in that game to
read their compressed chunks, then appends authenticated custom records and
verifies the reconstructed bytes against the exact in-game-tested bundle
hashes. No extracted stock bundles or native DLLs are shipped.

`InstallerEngine` validates every managed file and payload before the first
game write, guards running game processes and reparse-point paths, journals
writes with exact backups, repairs only known stock or missing owned files,
and surgically edits the one RainbowBarrels load-order line. Unknown game
builds, unexpected resources, Vortex-managed mod paths, or unowned prior
installations are rejected.

Development build and disposable fixture test:

```text
dotnet build installer/RainbowBarrels.Installer/RainbowBarrels.Installer.csproj -c Release
dotnet run --project installer/RainbowBarrels.Installer.Tests -c Release -- --package <active-RainbowBarrels-directory> --game <read-only-Darktide-directory>
```

The `--game` check reads only the already identified, pristine frag-grenade
stock bundle and game's Oodle decoder and compares its decoded SHA-256 with an
independent Python decoding. The other tests generate **synthetic** stock
bundles in `%LOCALAPPDATA%\Temp\opencode`; they test the real payload's install,
repair, uninstall, conflict rejection and failure rollback without touching
the installed game. Synthetic fixtures do not prove acceptance of stock
compressed release inputs; the recipient must test the release candidate on
a clean, supported game installation.

Generate the payload from authenticated, mod-owned candidate outputs:

```text
python -B resource/build_release_payload.py
```

The generator is intentionally one-shot and refuses to overwrite an existing
`payload/`. The payload belongs to the exact Lua build specified in its
manifest. Release ZIPs must be built via the workspace's canonical
`tools/release-mod.ps1 -Mod RainbowBarrels -Profile Installer` wrapper, which
validates Lua and publishes the reviewed WinForms output allowlist.
