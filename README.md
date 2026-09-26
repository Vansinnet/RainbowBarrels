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
   Remove any earlier experimental `RainbowBarrels` mod folder first, then
   extract the complete new folder into the game's `mods` folder,
   so you have `mods/RainbowBarrels/RainbowBarrels.mod`. Keep the `bin/`,
   `payload/` and `scripts/` folders inside it. You can instead install the
   ZIP through your mod manager, as with Polychromatic.
2. Add `RainbowBarrels` to `mods/mod_load_order.txt`, or enable it through your
   mod manager. Start Darktide and select colors in Mod Options.

No installer executable, extra restart or .NET runtime is required. The mod
serves its two rebuilt effect bundles and 1,098 material streams from its own
folder using Asset Redirect v2. It does not edit files under the game's
`bundle/` directory. All redirects must succeed before custom barrel effects
are used; an incomplete or outdated installation leaves barrel effects stock.
If a redirect reports `restart_required`, restart Darktide.

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
resource paths and select different effects in their hooks. A user confirmed
the previous RainbowBarrels RC working alongside RainbowFlame; the new
redirect-based combination has not been separately tested in game.

Previous-release client testing in a regular dedicated-server mission
confirmed the explosive-barrel effect, green fire-barrel ground fire at hue
120, blue ground fire at hue 240, and the corrected ground color layer.
With fire customization disabled, new fires appeared stock yellow/orange.
The direct-install path and dedicated-server-process execution have not been
independently verified for this version. Included resources and ZIP contents
are hash-checked; see [CHANGELOG.md](CHANGELOG.md), [LICENSE](LICENSE) and
[NOTICE](NOTICE).
