# RainbowBarrels changes

## 1.1.0

- Install by copying the complete mod folder into `mods` or using a mod
  manager, with no separate installer or .NET runtime.
- Serve two authored effect bundles and 1,098 material streams through Asset
  Redirect v2 from Polychromatic 1.0.1, without editing the game's files.
- Fall back to stock barrel effects if any required redirect is unavailable.

## 1.0.0

- Enable custom colors for both explosive barrels and fire barrels by default
  on fresh installations; preserve each player's saved choices.
- Promote the tested 360° barrel and ground-fire effects and Windows installer
  from the release candidate without changing the effect resource contracts.
- Document the RC uninstall prerequisite and user-reported RainbowFlame
  coexistence test.

## 0.1.0-rc.1

- Separate 0–359° colors for explosive-barrel and fire-barrel explosions.
- Recolor newly created, matching fire-barrel ground flames, edge effect, and
  the particle color graph responsible for warm floor highlights.
- Preserve stock effects when an option is disabled and avoid changing shared
  `prop_fire` templates.
- Add a build-pinned Windows installer with authenticated custom-resource
  payload, install/repair/uninstall, receipts, and rollback.
- Keep the installer action buttons accessible at Windows display scaling and
  smaller window sizes.
