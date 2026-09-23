# RainbowBarrels

RainbowBarrels independently recolors explosive-barrel explosions, fire-barrel
explosions, and the lingering ground fire from **new** fire-barrel explosions
in Warhammer 40,000: Darktide. Each barrel type has a separate on/off switch
and a 0–359° color setting. Gameplay damage, sound, and networking are not
modified. Other liquid fire keeps its original effects.

## Requirements

- Darktide Mod Loader (DML) and Darktide Mod Framework (DMF).
- Darktide Steam build `24735202`, executable `1.3.770.210`, Windows x64.
- Microsoft [.NET 10 Desktop Runtime](https://dotnet.microsoft.com/en-us/download/dotnet/10.0), x64.
- The two supported stock game bundles must be intact before the first
  installer run. A manually staged development copy or another resource
  replacement is not a stock installation and cannot be adopted.

## Install the release candidate

1. Download the complete `RainbowBarrels.zip` release candidate from the
   [GitHub Releases page](https://github.com/Vansinnet/RainbowBarrels/releases).
   Check its `.zip.sha256` value and extract the **entire** ZIP into one folder.
2. Close Darktide. Start `RainbowBarrels.Installer.exe` and select the
   `Warhammer 40,000 DARKTIDE` installation folder if needed.
3. Choose **Install**. The installer verifies build, executable, DML/DMF,
   stock resource hashes, custom payload hashes, and existing target paths
   before changing any game files. It reconstructs two game bundles from the
   user's verified stock bundles and authenticated custom records. Its
   bundled custom materials do not contain stock bundle copies.
4. Start Darktide and open **Mod Options > RainbowBarrels**. Setting changes
   affect new barrel explosions and new fire patches, not effects already in
   progress.

Keep the installer DLL, `RainbowBarrels/`, and `payload/` beside the EXE.
Copying the Lua mod folder alone does not install the required custom game
resources. The installer has no network or account access. It loads the exact
hash-checked `oo2core_9_win64.dll` shipped with the installed game solely to
decode authenticated stock bundle chunks.

The installer is unsigned. This is a **release candidate for user testing**, not
a signed production installer. Use only the link in the official GitHub
repository and verify the ZIP hash. It will refuse any changed, unsupported
or previously modified stock bundle rather than overwrite it.

### Repair and uninstall

Close Darktide and run the **same release candidate**. **Repair** restores a
missing owned file or stock-overwritten bundle when an exact ownership receipt
and stock backup still exist. **Uninstall** verifies owned files, restores
stock bundles from those backups, deletes only RainbowBarrels-owned additions,
and removes only its own `mod_load_order.txt` line. Other Vortex/user entries
are preserved. Backups and receipts live under
`%LOCALAPPDATA%\RainbowBarrels\`.

The installer does not automatically adapt to a new game build. Wait for a
compatible release after a Darktide update; never use an older installer to
restore obsolete game assets. Vortex-managed RainbowBarrels installations
and manual resource replacements are not currently adopted by this installer.

## Tested behavior

User testing as a client in a normal mission on a dedicated server confirmed
the explosive-barrel effect, green fire-barrel ground fire at hue 120, blue
fire-barrel ground fire at hue 240, and the corrected ground color layer. With
fire customization disabled, new fires appeared stock yellow/orange. Separate
unrelated `prop_fire`, the final bundle with VFX Swapper enabled, installer
operation on another user's fresh game, and server-process execution have not
been confirmed in game. The local development build and the release payload
must be tested independently before claiming release parity.

## Development and ownership

`resource/` and `installer/` contain the source and tools. [Research and
validation](RESEARCH.md) records exact build, assets, alternatives, and test
limitations. `analysis/` is local research material and is excluded from Git
and releases. The installer payload contains authenticated custom insert
records and materials, not complete extracted game bundles. See [LICENSE](LICENSE)
and [NOTICE](NOTICE) for ownership and third-party rights.
