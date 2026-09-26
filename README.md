# RainbowBarrels

RainbowBarrels independently recolors explosive-barrel explosions, fire-barrel
explosions, and lingering ground fire from **new** fire-barrel explosions in
Warhammer 40,000: Darktide. Choose a hue from 0–359° for each barrel type or
turn either effect off under **Mod Options > RainbowBarrels**. Both switches
are on by default for new users; existing saved choices are preserved.
Changes affect new effects, not explosions or fire patches already in progress.
Gameplay damage, sound, networking and unrelated liquid fire are unchanged.

## Requirements

- Darktide Mod Loader (DML) and Darktide Mod Framework (DMF), Windows x64.
- The two original bundles must match the stock SHA-256 hashes for Steam build
  `24735202` (Darktide executable `1.3.770.210`). When a game update changes
  either bundle, the corresponding redirect is skipped until the mod is updated.

## Installation

1. Download `RainbowBarrels.zip` from the latest
   [GitHub release](https://github.com/Vansinnet/RainbowBarrels/releases).
   Remove an older or experimental `RainbowBarrels` mod folder first so no
   stale files remain, then extract the complete new folder into `mods`,
   so you have `mods/RainbowBarrels/RainbowBarrels.mod`. Keep the `bin/`,
   `payload/` and `scripts/` folders inside it. You can instead install the
   ZIP through your mod manager.
2. Add `RainbowBarrels` to `mods/mod_load_order.txt`, or enable it through your
   mod manager. Start Darktide and select colors in Mod Options.

No installer executable or .NET runtime is required. The mod includes
[Reforge](https://github.com/Vansinnet/Reforge) (`reforge.lua` and
`bin/reforge.dll`), an open-source library that serves the mod's files in
place of the game's while Darktide runs. On startup RainbowBarrels registers
two replacements for stock bundles and 1,098 new material streams. Reforge
checks both original bundles' SHA-256 hashes before serving the mod's files.
No files under the game's `bundle/` directory are edited. Type `/reforge` in
chat to list every replaced file and its state.

Custom barrel effects are enabled only when **all 1,100 redirects** are active
or shared. If a file is missing, an original bundle has changed, or the
library cannot load, barrel effects stay stock and the mod reports the
incomplete status in the log/chat. If it reports `restart_required`, restart
Darktide. A normal installation takes effect on the first launch.

### Upgrading from an installer release

With Darktide closed, run **Uninstall** using the RainbowBarrels 1.0.0 (or
earlier RC) installer **before** installing this version. That restores the
original game bundles and removes the old installer-owned material streams;
otherwise the new stock-hash check will not pass. If you used a manual
development deployment, restore only its owned files using its original
rollback receipts. You need not remove unrelated mods.

To update a direct-install version, replace its `mods/RainbowBarrels` folder.
To uninstall it, remove that folder and its load-order entry; this version
does not require game-file restoration. A changed game build may need a new
mod version before custom effects return.

## Compatibility and testing

RainbowFlame is optional and not included. The two mods target separate
resource paths and select different effects in their hooks; both use Reforge
and share one copy of it. RainbowBarrels replaces no file that Polychromatic
replaces, so the two can be installed together.

With Reforge, `/reforge` reported all 1,100 files active in game and the
barrel effects worked, with no errors. That test used the previous,
uncompressed bundles. The bundles are now Oodle-compressed like the game's
own, with identical contents.

Previous-release client testing in a regular dedicated-server mission
confirmed the explosive-barrel effect, green fire-barrel ground fire at hue
120, blue ground fire at hue 240, and the corrected ground color layer.
With fire customization disabled, new fires appeared stock yellow/orange.
The direct-install path and dedicated-server-process execution have not been
independently verified for this version. Included resources and ZIP contents
are hash-checked; see [CHANGELOG.md](CHANGELOG.md), [LICENSE](LICENSE) and
[NOTICE](NOTICE).
