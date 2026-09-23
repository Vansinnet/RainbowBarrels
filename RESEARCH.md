# RainbowBarrels: barrel explosion resource investigation

Status: a hash-pinned local development candidate is installed for testing.
The physical no-op package rendered both barrel explosions normally in one
user-reported regular mission. A subsequent test found the explosive-barrel
color correct and the fire-barrel explosion lighting blue, while separately
spawned ground flames remained orange. New persistent-fire resources exist
only as offline candidates. This is not a release. Extracted stock resources
and authored candidates under `analysis/` are development-only and must not
be included in a release payload.

## Build and source provenance

The inspected Steam app manifest reported build `24735202`, and the installed
executable reported version `1.3.770.210`. Target paths and their hash-pinned
resource records are recorded in
`analysis/stock-particles-24735202/provenance.json`; the referenced bundle
SHA-256 values are:

| Source bundle | SHA-256 | Contents used |
| --- | --- | --- |
| `bundle/d2b0b18252164f5b` | `86d24e1dd5796d4cbc2dee764b1860b2b327c21dfbad5e4f45083d1c9c045fa9` | standalone fragment explosion |
| `bundle/98bb14b1d247a0c8` | `9086f577b55278286bc5cd72de529300d61ba15d2612ad66a1cbe8b272d4da48` | both explosion particles and material index |

The two copies of the fragment explosion particle are byte-identical (SHA-256
`6e099c7138f8de0b0b2a0e56e4ce8c9717b40a7f38e6c2b26fdfd276abd092d7`).
The fire-barrel explosion particle has SHA-256
`c175cf1783f168f08c3cf9b8dd18ac9d2214062d6c9936c0cce058de4ac5abdd`.
Both bundle paths were absent from the known RainbowFlame managed-file manifest
and the Vortex deployment list. This does not independently prove every other
installed file is pristine.

`resource/inspect_stock.py` performs index-only discovery by exact particle
identity. `resource/analyze_effects.py` decodes only the two identified source
bundles and extracts the three named particle records. `resource/profile_particles.py`
enumerates their bounded cloud records. `resource/resolve_materials.py`,
`resource/profile_materials.py`, and `resource/profile_parents.py` follow the
selected material references, verify installed file identities, and profile
material parents. The ten directly referenced material streams and their hashes
are recorded in `analysis/stock-materials-24735202/provenance.json`.
The three inherited parent materials and their hashes are recorded in
`analysis/stock-parents-24735202/provenance.json`; they were copied only after
confirming the restored `be93` stream matched its known original SHA-256.
`resource/profile_shaders.py` identifies framed shader stages; the selected
pixel-shader disassemblies and SHA-256 values are retained under
`analysis/shader-color-trace-24735202/` and
`analysis/shader-remaining-24735202/`. The former contains eleven pixel programs;
the latter contains nineteen additional distinct pixel programs from the other
direct and inherited material families. An earlier `shader-trace-24735202/`
contains the corresponding vertex-stage investigation, not color evidence.

## Rendering and mod scope

`ExplosionTemplates.explosive_barrel` uses
`content/fx/particles/explosions/frag_grenade_01`. That particle is also used
by other explosions, including grenades: globally replacing it would be wrong.
`ExplosionTemplates.fire_barrel` uses
`content/fx/particles/destructibles/explosive_barrel_explosion`. The former
particle has 12 cloud systems; the latter has 18, including multiple billboard
material graphs. They share at least one material identity. Both need isolated
effect variants selected by explosion template so their eventual color controls
can be independent and other explosions remain stock.

The stock material `be9333164c3ddf4a`, used by one fire-barrel cloud, was
initially RainbowFlame's installed replacement. Its installed SHA-256 was
`b353109dbe0742b18149a58fdac9f92da4c41f1200339abbb89fc1c783011d29`.
After the user restored the game, the file
`bundle/data/c5/c54a5bfcf52f138d` matched RainbowFlame's recorded **stock**
size 498300 and SHA-256
`886bb655bbc3ffa675ff33bdc49f80ef8a2cd2e45c8f502b97ea9539bbe1bd7e`.
The stock bytes alone do not show that their particle RGB channels provide an
arbitrary runtime tint. Other directly referenced materials have scalar-only
exports or inherited shaders. The color-bearing shaders and the complete
particle/material reference graph still need targeted disassembly, proven
binding semantics, isolated authoring, no-op reconstruction, and game testing
before creating user-facing sliders.

Eleven pixel shaders from four direct material families were independently
decoded and disassembled. For example, material `362b6999973734bf`'s first
pixel shader multiplies independent input RGB channels by sampled RGB at
`analysis/shader-color-trace-24735202/362b6999973734bf-01.ll.txt:347-368`.
Material `9cda55b98bbfc8ff` instead emits sampled texture RGB scaled by one
common scalar at `9cda55b98bbfc8ff-01.ll.txt:318-339`. Material
`082914d27a058793` combines two colored paths plus additive input RGB at
`082914d27a058793-01.ll.txt:644-687`. These are distinct contracts; none is
evidence that one existing material parameter tints all barrel clouds. Three
inherited shader *families* have 32, 104, and 107 framed programs respectively,
but many bytecode programs repeat. All 30 distinct direct and inherited pixel
programs were extracted and disassembled; their color, alpha, texture, and
feedback paths still need classification before an exact arbitrary-hue feature
can be claimed. Shader counts are not a claim that every program needs mutation.
`resource/classify_pixels.py` shows 22 of these distinct programs write target
RGBA; eight have no color-target output and are feedback/non-color paths.
This is a syntactic output inventory, not proof that all emitted light and
particle systems have been colored. The non-billboard cloud and light records
still need separate review for the requested all-visible scope.

`resource/author_pixel_programs.py` has now assembled and independently signed
hue-controlled DXIL for all 22 color-writing program entries. It verifies each
original DXBC hash, exact material-buffer binding, output channels, regenerated
field reflection, and byte-identical SFI0/ISG1/OSG1/PSV0 signatures. The
candidate shader bytes, typed modules, and SHA-256 evidence are under
`analysis/hue-pixel-programs-24735202/`. These are offline shader candidates,
not yet registered material variants. Some material families have full GPU
buffers, requiring verified buffer growth in addition to shader authoring.

`resource/locate_light_colors.py` identified one ColorGraph-shaped RGB curve
at visualizer-relative offset 352 in each of the four type-1 light clouds
(two per explosion). The ten time keys, 30 RGB floats, and trailing active-key
count account for the exact observed key shapes. `resource/author_light_graphs.py`
recolored only the active RGB triples to green while preserving each key's
maximum channel amplitude; it proved a byte-exact inverse and reread all four
curves. The two offline particle candidates and hashes are in
`analysis/light-green-trial-24735202/report.json`. This does not show that
the engine accepts their visual encoding or that live material parameters can
recolor the lights. To provide an integer-degree color wheel for light curves,
each selected hue may need its own indexed particle variant, while the
billboard materials can use the authored scalar hue control.

The requested scope covers all visible explosion layers, including smoke and
debris. Do not silently reduce this to just the initial flash or fire layer.

### First material-authoring control

The first bounded authoring target is the fire-barrel billboard material
`9cda55b98bbfc8ff` (stock SHA-256
`5232ffc199ec0e11cb80558ed8604fa09bfb411c56a299d46640724ed5d64ebd`).
`resource/experiment_tint.py` produced an unchanged-body DXIL roundtrip and a
fixed-green end-stage transform. `resource/experiment_hue.py` then added a
single scalar `rainbow_barrels_hue` export at offset 52 in this material's
pixel shaders, preserving the texture sampling and alpha output. DXC validated
the signed program, and `resource/verify_hue.py` confirmed the export and
byte-identical shader signature chunks. This is an offline GPU program result,
not an observed in-game tint.

`resource/profile_exports.py` verified byte-identical stock material and
three-group shader-table roundtrips. `resource/author_material.py` verified a
whole-material no-op rebuild, then added the scalar export to the material
template, all three registration groups, and the default-value table. It
replaced the three pixel programs but retained the three original vertex
programs. `resource/verify_material.py` independently parsed and compared the
authored candidate. The retained offline material is
`analysis/hue-material-trial-24735202/hue.material`, SHA-256
`c0c68e9161ab66e033589314daa825917917a4c93b9c56d2dc6e41039e9981e8`.
It is not installed, indexed, or game-tested. In particular, native lookup of
the newly exported scalar and creation of a separate particle/material identity
remain unproven; this file must not be treated as a distributable mod.

`resource/audit_families.py` now passes byte-identical stock template,
registration-table, and default-table roundtrips for all ten directly
referenced material streams and three inherited parents (three child streams
have no shader). `resource/audit_buffers.py` locates material-export buffers
and their current extents. Most shader families have room for one scalar, but
`be9333164c3ddf4a`, `debe1ef92005d87e`, and `e14900c258cc9b8e` have full
material buffers. `resource/author_material_families.py` and
`resource/author_full_materials.py` built all ten shader-bearing material
families; `resource/verify_families.py` and
`resource/verify_full_materials.py` independently checked their template,
registration, default-value, program, metadata, and buffer-relocation deltas.
The three full-buffer families enlarge by 16 bytes. Other original material
programs are unchanged; this is still only offline acceptance.

`resource/build_green_bundle.py` produced a two-particle, 13-material isolated
green control. `resource/build_hue_wheel.py` expanded that design to all 360
integer hues for each barrel type. Its candidate
`analysis/hue-wheel-bundle-24735202/bundle/98bb14b1d247a0c8` has SHA-256
`a0a15fcde68bbd2d7a4ec0cd998bd7d143d2999d3d0b8a74baa60340b529cff9`.
The readback script verified 423 unchanged stock resources, 13 added material
registrations and streams, and 720 added particle resources, each with both
colored light curves and named material clouds. Original grenades still route
to their stock particle identity. The 13 material streams are additions under
`bundle/data/rb/`, not writes to shared original material streams.
`resource/prepare_deployment.py` completed a read-only preflight against the
installed build, original bundle SHA-256, absent new material paths, and absent
deployed RainbowBarrels folder. Its separate identity-preserving stored no-op
bundle has SHA-256
`218dffc31c4a88b1e3d5a61c2120c39cae24b3e38ea12cf17a753ed1b19675d1`.
The preflight report is under `analysis/deployment-preflight-24735202/`.
`mods/mod_load_order.txt` is managed by Vortex, so any local test must record
its exact original bytes and restore them only if still unchanged by Vortex.
No game-file mutation followed from that read-only preflight alone. The
subsequent explicitly approved local deployment is recorded below.

### Local runtime test (in progress)

The user authorized a staged test on build `24735202`. With Darktide closed,
`resource/deploy_test.py` backed up stock bundle
`98bb14b1d247a0c8` (SHA-256
`9086f577b55278286bc5cd72de529300d61ba15d2612ad66a1cbe8b272d4da48`)
and temporarily installed its identical-content, stored-chunk no-op bundle
(SHA-256 `218dffc31c4a88b1e3d5a61c2120c39cae24b3e38ea12cf17a753ed1b19675d1`).
In a regular `coop_complete_objective` mission the user reported that both an
explosive-barrel and a fire-barrel explosion looked normal without a crash or
missing effect. LuaExec PID `3792` gave only a read-only context snapshot:
game mode `coop_complete_objective`, local player and unit ready; it did not
inspect rendering. Exact observations and rollback receipt are under
`analysis/deployment-runs/20260922T225455Z-861f2c6c/`.
After Darktide closed, the no-op bundle was restored to the pinned stock SHA.

`resource/deploy_candidate.py` then installed the offline color candidate
bundle (SHA-256
`a0a15fcde68bbd2d7a4ec0cd998bd7d143d2999d3d0b8a74baa60340b529cff9`),
thirteen new `bundle/data/rb/` streams, the four Lua/mod files under
`mods/RainbowBarrels/`, and the `RainbowBarrels` load-order entry. The game
was closed for all file changes. Receipt, exact owned-file hashes, original
bundle/load-order backup, and rollback command are recorded at
`analysis/deployment-runs/20260923T074518Z-ac639c88/receipt.json`.
The load order is Vortex-managed: rollback refuses to overwrite it if Vortex
changes it during testing. In the next regular `coop_complete_objective` mission,
LuaExec PID `16704` confirmed RainbowBarrels present/enabled, explosive hue 120,
fire hue 240 and a living local player unit. The user reported that the
explosive barrel was "perfect". A supplied screenshot showed blue light
around the fire barrel but a large orange, stationary patch of flames. The
screenshot was conversation evidence, not saved as a local artifact. This is
a confirmed partial fire-barrel result; it is not a complete fire-color pass.

The Lua controller under `scripts/mods/RainbowBarrels/` defines independent
on/off and 0–359 hue options, selects variants on locally rendered
`Explosion.create_husk_explosion` events and sets the hue scalar as each
selected particle is created. The original `explosive_barrel` template is
also used by explosive luggables: client husk VFX does not expose source-unit
kind, so they will share that option. The locally installed Lua copy is still
the initial explosion-only version. The active development source now includes
an *undeployed*, temporary, bounded ground-fire matching probe. Changed runtime
Lua passed LuaLS and syntax checks; new resource loading, ground-fire binding,
other mission/authority contexts and disabled-effect lifetime remain unobserved.

The fire-barrel explosion is separate from its subsequently spawned ground-fire
area. The observed orange ground fire requires a separate resource and client
selection path to meet the requested visible-color scope.

### Persistent fire from the fire barrel (offline candidate)

`HazardPropExtension._trigger_hazard` calls
`LiquidArea.try_create(..., LiquidAreaTemplates.prop_fire, barrel_unit)` after
the explosion (`darktide-source/scripts/extension_systems/hazard_prop/hazard_prop_extension.lua:267-305`).
`prop_fire` uses `fire_lingering` and `fire_lingering_edge`
(`scripts/settings/liquid_area/liquid_area_templates/prop_liquid_area_templates.lua:5-21`).
On a dedicated client, `LiquidAreaUnitTemplate.husk_init` transmits the template
identity, but not the source barrel unit
(`scripts/extension_systems/unit_templates/liquid_area_unit_template.lua:39-47`).
Changing the shared `prop_fire` template would also affect unrelated map fires.

`resource/inspect_liquid_effects.py` verified byte-identical stock particles
in their standalone and small shared bundles. The five direct/parent stock
material streams and their SHA-256 are retained under
`analysis/liquid-stock-24735202/`. Six distinct color-output programs were
authored with a scalar hue export and signed by DXC; three parent material
streams plus two child-parent redirects passed offline readback under
`analysis/liquid-hue-materials-24735202/`.
`resource/build_liquid_bundle.py` preserves all 103 stock records of bundle
`b224998193576995` and adds two cloned particles plus five material records.
The changed package SHA-256 is
`6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d`;
its physical no-op control SHA-256 is
`ccdb03b329566349708f6aee5076ea069ad980744f3a667fc64fadd5cdf49337`.
`resource/verify_liquid_bundle.py` verified the new index and all stream
references. The previous deployment authorization covered only the first
bundle and its thirteen streams; the user separately approved this second
bundle, five additional streams, and two updated Lua files.

The development Lua source records at most four recent boxed fire-barrel
explosion positions for up to four gameplay seconds, then considers only nearby
new `prop_fire` extensions before selecting the custom filled/rim particles.
It does not mutate stock templates or unrelated liquid areas. A temporary
`RainbowBarrels ground probe` logs at most eight edge events per mission.
Client RPC ordering, the matching radius, and visible effect remain runtime
questions; remove the probe before finishing.

In the second staged test, `resource/deploy_ground_test.py` backed up stock
bundle `b224998193576995` with SHA-256
`775762aae54cfd5313856f8b097e2527774600e92df896d375e4af6b8916376d`
and installed its identical-content stored no-op bundle with SHA-256
`ccdb03b329566349708f6aee5076ea069ad980744f3a667fc64fadd5cdf49337`.
The user reported a normal orange fire-barrel ground patch, the previous blue
explosion glow, and no crash in a regular mission; the game was then closed.
The no-op bundle was restored to its stock SHA. Receipt and observations are
under `analysis/deployment-runs/20260923T111352Z-d84f92bf-ground-noop/`.

With the game closed and the user-approved second scope, the altered package
(SHA-256 `6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d`),
five added streams and two updated Lua files were staged. The previous
explosion package and 13 streams were left untouched. Backup, owned hashes
and rollback command are in
`analysis/deployment-runs/20260923T112114Z-23f7533d-ground-candidate/receipt.json`.
This changed ground-fire effect has **not yet been observed in game**.
Between tests, Vortex changed unrelated entries in `mod_load_order.txt` but
kept exactly one RainbowBarrels entry. The second deployment leaves that
file untouched; the original candidate rollback has a surgical, separately
previewed remove-only-owned-line path that preserves other Vortex changes.

At the first launch with the ground candidate, the user supplied an error
screenshot: DMF reported nonexistent `LiquidAreaExtension._calculate_broadphase_size`
and `LiquidAreaExtension.set_drawer` hooks. Both methods exist later in the
current game source (`liquid_area_extension.lua:151,799`) and are hooked by
other installed mods (`danger_zone` and `vfx_swapper`). RainbowBarrels had
eagerly required the liquid-area extension modules, possibly exposing their
classes before those methods and other mods' delayed hooks were ready. The
development code now uses `mod:hook_require` for the exact game files and
registers its safe `init` hooks only after the files finish loading
(`dmf-source/scripts/mods/dmf/modules/core/require.lua:66-81`,
`modules/core/hooks.lua:452-476`). LuaLS and Lua syntax passed. With separate
explicit approval and the game closed, only the deployed `RainbowBarrels.lua`
was updated; the original deployed SHA-256
`eca362413fa4eac83c4f56dc09ff2a37e203ccc5129509d7519bf503fbcbba7b`
and new SHA-256
`076c912a811783a169cc1cb13cf3c26ab173b037d0a2847db90b366722755d02`
are recorded under `analysis/deployment-runs/20260923T114354Z-7ba643fe-hook-fix/`.
The next startup reached a regular mission; no repeat of the hook error was
reported. No other mod, bundle or load-order file was changed by this hotfix.

In that mission, a user screenshot still showed yellow filled ground flames
with Fire hue 240. The focused LuaExec log reported a barrel explosion and
`prop_fire` at gameplay time 271.45, `match=true`, `dist_sq=1.34`, `age=0`.
A read-only settings snapshot found the user's installed VFX Swapper enabled
with `replace_fire_barrel_vfx` set to stock
`content/fx/particles/liquid_area/fire_lingering`. Its deployed 1.2.2 source
overwrites `_vfx_name_filled` before each
`HuskLiquidAreaExtension._set_liquid_filled` and
`LiquidAreaExtension._set_filled` call. That explains why a successful local
explosion-to-area match still spawned orange filled flames.

The development Lua source now scopes the selected liquid extension during
each synchronous filled-cell call and redirects only stock `fire_lingering`
to the custom effect in the existing `World.create_particles` hook. The scope
is restored even when the wrapped call errors. This makes the substitution
independent of whether VFX Swapper is inside or outside our hook in the chain;
other `prop_fire` instances are not selected. LuaLS/syntax validation passed.
With a separate one-file approval and Darktide closed, the Lua change was
installed from previous SHA-256
`076c912a811783a169cc1cb13cf3c26ab173b037d0a2847db90b366722755d02`
to new SHA-256
`e80157ec1a7f95423584acbe2cd3eb1307c4ce19619050c239c4bdbf4ac8fc38`.
Backup and rollback receipt are under
`analysis/deployment-runs/20260923T132814Z-f6c54d3d-fill-fix/`.
No bundle, material or Vortex file changed. **The new filled-cell redirect
has not yet been tested in game**; temporary probe messages remain capped at
eight events per mission until that result is known.

The Lua redirect was then tested in a regular `coop_complete_objective`
mission on local process 27428. The read-only preflight observed a living
player, RainbowBarrels enabled, Fire hue 240, and VFX Swapper enabled with its
stock fire-barrel replacement. A 60-second target log captured the explosion,
`prop_fire match=true dist_sq=2.79 age=0`, and six `filled VFX redirected`
events with no RainbowBarrels error. The filled flames were visibly red at
hue 240. A user-driven comparison at hue 120 again left the filled flames red
while the surrounding explosion light correctly became green. This confirms
the particle redirect and light color, but does not independently prove that
the filled cloud names or material scalar setter resolve successfully.

Offline inspection suggested one cause: filled clouds bind shaderless child
materials `d11c8f091a39ef54` and `62b838cfa247b2ca`. Their custom parents have
the `rainbow_barrels_hue` shader registration, but each child owns a material
reflection/value table without that export. A v2 candidate therefore preserves
all shader parents, textures and child overrides while appending only the hue
reflection row and a zero default to each child. The child streams grow by 24
bytes: `91db160e1872a6af` from 324 to 348 bytes, SHA-256
`55e69d301287965048bed3c6e689d78f57d1fecc047de5a3659844fe8ceeb6b0`;
`c830ae27aba6f614` from 416 to 440 bytes, SHA-256
`6b36e5b495aff3d258d6044f122ce21354ddc62c6fd322ec7a752947bdbd9190`.
Independent readback verifies exact parent preservation, export offsets 64/68,
one appended scalar per child and no unrelated stream or bundle delta. The
installed bundle remains SHA-256
`6d83ab857ce0288a9ba945d1e4ac7095bc4f1d433fd9992c08c7a4baf40dde3d`.
Deployment preflight passed. With separate explicit approval and Darktide
closed, both v2 streams were installed with exact
backups under
`analysis/deployment-runs/20260923T142017Z-b17a5aec-child-exports/`.
The receipt records state `child_exports_installed`; the bundle, Lua and
Vortex load order remained unchanged. A second regular
`coop_complete_objective` test in PID 7612 at Fire hue 240 verified the exact
v2 stream hashes and logged `prop_fire match=true dist_sq=3.08 age=0` plus six
filled-cell redirects without a target error. The user's screenshot still
showed red/orange filled flames and blue surrounding illumination. Thus the
child-export-only hypothesis was insufficient; color remains **Runtime
pending**. Neither run established whether the scalar setter reached named
cloud materials or whether the GPU shader consumed the assigned value.

A further **undeployed** two-event diagnostic in the development Lua checks
`World.has_particles_material` for the two filled clouds and records each
setter's return and requested normalized hue at the existing cell-creation
edge. Current game code performs the same check immediately after particle
creation (`darktide-source/scripts/components/particle_effect.lua:107-114,
161-187`). This query cannot prove GPU-buffer delivery, but it distinguishes
missing named clouds from a subsequent material/buffer problem. LuaLS and
syntax validation passed. With separate explicit approval and Darktide closed,
the diagnostic Lua was installed from SHA-256
`e80157ec1a7f95423584acbe2cd3eb1307c4ce19619050c239c4bdbf4ac8fc38`
to SHA-256
`3bb1fc0e64f2ab12439a73bba3a916f75d4c823140a7cc58c2fabdf10411efbd`.
Backup and rollback receipt are under
`analysis/deployment-runs/20260923T144943Z-edb11c92-scalar-probe/`.
Bundles, material streams and Vortex list remained unchanged. The scalar
presence/result messages were then observed in a regular
`coop_complete_objective` mission on PID 6932 at Fire hue 240. The local log
recorded `match=true dist_sq=1.71 age=0`, six filled-cell redirects, and
`present=true hue=0.667 result=nil` for both
`RainbowBarrels_ground_filled_00` and `_01`. The user's screenshot still
showed red/orange filled flames despite blue surrounding light. `nil` is not
an error signal: current Darktide callers do not inspect the setter's return
(`scripts/components/particle_effect.lua:173-187`). Cloud naming and normalized
Lua input are therefore confirmed; material constant-buffer delivery or a
different rendered visual layer is still unresolved.

To separate runtime scalar delivery from static material/shader visibility,
`resource/build_liquid_blue_defaults.py` authored an **undeployed** hue-240
default test for the five owned liquid streams. It changes one four-byte hue
value in each material template and an additional four-byte GPU default in
each of the three shader-bearing parents; no shader bytecode, texture,
reflection, resource identity or bundle changes. Independent verifier
`resource/verify_liquid_blue_defaults.py` reconstructed every candidate from
its pinned v2 stream by changing exactly those float offsets and no other
bytes. `resource/deploy_liquid_blue_defaults.py preflight` checked the five
currently installed v2 streams, diagnostic Lua, liquid bundle and Vortex list
without writing game files. Following separate approval and a confirmed
Darktide process exit, the five diagnostic streams were installed with unique
hash-pinned backups at
`analysis/deployment-runs/20260923T152446Z-3ae58d62-blue-defaults/`.
Bundle, Lua and Vortex list were unchanged. Native acceptance and visible
blue flames were then tested in a regular `coop_complete_objective` mission
on PID 27108 at Fire hue 240. The read-only preflight verified all five fixed
blue stream hashes. A 60-second capture observed `prop_fire match=true
dist_sq=1.16 age=0`, six filled-cell redirects and both named clouds present
at requested runtime hue `0.667` (native setter returned nil as before).
The user reported **"nu! perfekt!"** and supplied a screenshot of visibly
blue flames. This establishes acceptance and visible blue at hue 240 with
static blue defaults, not arbitrary runtime hue: both the three shader-parent
defaults and two child defaults changed together, so their individual
contributions remain unproven. At that stage other ground hues, unrelated
`prop_fire`, mission transitions and server-process execution were unobserved.

While that fixed-blue build remained installed, the user selected Fire hue
120 and exploded another barrel; the ground flames **remained blue**. Thus
material defaults dominate the attempted per-cell dynamic setter, even after
the child scalar exports were added. A read-only `deploy_liquid_child_only.py
preflight` now pins an isolating follow-up: restore only the three large
shader-bearing parent streams to their v2 zero-default versions while leaving
the two small child streams at static blue. No game files changed during this
preflight. With separate approval and a confirmed Darktide process exit, the
three parent streams were installed from their pinned v2 payloads, with unique
backups under
`analysis/deployment-runs/20260923T162039Z-fa106e3b-child-only/`.
The two blue child streams, bundle, Lua and Vortex order were unchanged.
Whether child defaults alone drive the visible flames is **Runtime pending**,
and determines whether 720 small hue variants are viable instead
of duplicating three large shader parents per hue.

The first child-only test was interrupted by a mission transition; no barrel
event occurred during that capture. A new game process, PID 20492, then
verified three v2 parent hashes and two blue child hashes, Fire hue 240 and a
normal `coop_complete_objective` mission. VFX Swapper was not enabled in that
session. The log recorded the match at `dist_sq=1.29` and both filled clouds
present. The user reported the result looked **roughly the same** as the
previous blue version, with yellow spots on the floor texture. This supports
blue filled flames from child defaults alone but does not establish that all
surface layers are blue. The template independently spawns a rim particle
(`prop_liquid_area_templates.lua:18-19`,
`husk_liquid_area_extension.lua:193-211`); its separate direct material is
still at the v2 default, so the rim is a candidate source for those spots,
not yet an observed attribution.

A green child-only test at hue 120 changes only the two
four-byte child hue values from blue `2/3` to green `1/3`, preserving the
shader parents, resources and material reflection. Exact-byte independent
verification and a read-only two-stream deployment preflight passed. With
separate user approval and Darktide closed, both green children were then
staged with exact backups under
`analysis/deployment-runs/20260923T170223Z-1991a1a1-green-children/`.
Shader parents, bundle, Lua and Vortex order remained unchanged. Its
runtime test in regular `coop_complete_objective` on PID 33240 verified both
green stream hashes, Fire hue 120 and an explosion-to-`prop_fire` match at
`dist_sq=1.28`. Both filled clouds existed. The user reported **"mycket bra!"**
with a screenshot of green flames; yellow/orange patches remained on the
surface. VFX Swapper was disabled in this session. The capture also reported
97 dropped bytes, but the focused RainbowBarrels lines were present. This
establishes that shaderless child defaults can select a second ground hue
independently of the three large shader parents. The directly referenced rim
material is still at its v2 zero default and is the bounded next source
candidate for the orange/yellow surface layer.

`resource/build_liquid_hue_wheel.py` now generates a separate filled and rim
particle for each hue 0–359. Each filled variant binds two small shaderless
child material streams with an authored hue value; the independent rim variant
binds a direct shader material with both its template and shader GPU default
set to that hue. This adds 1,080 streamed materials and 720 particle records
to the existing b224 liquid bundle (110 old records preserved), for 1,910
total records. Candidate bundle SHA-256:
`ba72ce819fa19d2c7c9ba3449e58013c2a3b1247f109d082da32682a2b0aae31`.
For filled children, generated hues 120 and 240 are byte-identical to the
separately game-tested green and blue candidates. Independent verifier
`resource/verify_liquid_hue_wheel.py` checks all 360 values, every material
float-only delta, particle/material identities, references and the 110
unchanged bundle records. All passed offline; engine loading of the larger
bundle and rim color remain **Runtime pending**.

The development Lua selects these indexed ground effects at each new matched
fire-barrel area and keeps its selected filled effect on that area across
setting changes. It preserves the scoped stock-name redirect for VFX Swapper,
removes temporary ground/scalar probes, and keeps the established explosion
scalar path. LuaLS and Lua syntax passed for the changed file. Read-only
deployment preflight verified the five current streams, installed explosion
bundle, 1,080 unoccupied new stream paths, Vortex order and exact Lua/bundle
hashes; `resource/deploy_liquid_hue_wheel.py` has a unique-backup, hash-pinned
restore path. With separate approval and Darktide closed, the wheel was
installed. Its receipt and exact prior bundle/Lua backups are under
`analysis/deployment-runs/20260923T172524Z-2c23ccf6-ground-wheel/`;
1,080 new streams were individually written and hash-read back. The updated
bundle SHA-256 is
`ba72ce819fa19d2c7c9ba3449e58013c2a3b1247f109d082da32682a2b0aae31`,
and Lua SHA-256 is
`eda5aab1101ac5980b81a7e077c3f56f9f1f7e56f25e9d0ef9dd4a642b5e9991`.
The five prior liquid streams, explosion bundle and Vortex list were left
unchanged. In a regular `coop_complete_objective` mission (PID 5860), a
read-only preflight confirmed the exact installed bundle/Lua hashes, Fire
hue 120, a living local player and RainbowBarrels enabled. VFX Swapper was
not active. The user's screenshot shows clearly green filled ground flames
from a new fire barrel with the indexed wheel. Bright yellow/orange patches
remain on the floor even with the indexed green rim material, so the rim
material by itself does **not** explain all residual floor color. The user
then changed Fire hue to 240 and supplied a screenshot of blue filled ground
flames from another barrel in the same indexed-wheel build. Pale pink/orange
floor highlights remain visible. The remaining floor visual source,
unrelated fires and server-process execution were not established at that stage.

The user provided a later comparison at the same site. Warm patches were
visible while the ground-fire effect was present, then vanished after the
effect faded; blue transient haze lingered briefly. Source tracing found no
extra `prop_fire` VFX or decal spawn in `HazardPropExtension._trigger_hazard`
or `LiquidArea.try_create`: the fire barrel calls the explosion effect and
creates one liquid area whose template lists filled and rim particles. The
retained material disassemblies show the three unmodified liquid pixel
programs (`4cd51280796476b3-03`, `1cc58f33452ca960-03`,
`62c7bb3aa1cac9c2-08`) have no `SV_Target` color output; all identified
color-writing programs were hue-authored. That narrows, but does not prove,
the source of the warm floor patches; no additional resource is identified
with sufficient evidence for an edit.

Further focused byte inspection found a previously uncolored part of that
same known resource. `fire_lingering` has two material-bearing type-0 clouds,
one **type-2 cloud at index 2**, and one empty cloud. The cloned 360° particle
only rewrote type-0 material references; type 2 stayed byte-identical to
stock. The type-2 visualizer has an independently bounded 728-byte profile
and exactly one ColorGraph-shaped record at visualizer offset 480, mode 3,
with four active RGB keys `(0,0,0)`, `(255,255,255)`, `(229,229,229)`,
`(0,0,0)`. It is therefore an evidenced visual color source inside the
liquid fire, not proof of the renderer's semantic type or proof that it
accounts for every warm floor pixel. A separate stock explosion type-2
visualizer has a different 440-byte layout without this curve, so the two
are not treated as interchangeable.

`resource/build_liquid_floor_graphs.py` recolors only the two positive RGB
keys in that exact cloud for each of the 360 already-indexed filled effects.
No rim particle, material stream, shader, Lua, or resource identity changes.
Candidate b224 bundle SHA-256:
`7181ef9b900ad89bd5d43759c28f027fc3dbf9b2de68d0ff7beaa798c1900820`.
Independent `resource/verify_liquid_floor_graphs.py` passed byte-level
readback: 360 type-2 clouds contain hue-matched RGB curves, and all other
1,550 bundle records are identical. Read-only deployment preflight confirmed
the previously installed wheel bundle, Lua, 1,080 owned streams, explosion
bundle and Vortex order. With separate approval and a confirmed Darktide
process exit, only that bundle was staged from SHA-256
`ba72ce819fa19d2c7c9ba3449e58013c2a3b1247f109d082da32682a2b0aae31`
to SHA-256
`7181ef9b900ad89bd5d43759c28f027fc3dbf9b2de68d0ff7beaa798c1900820`.
Exact backup and rollback receipt are under
`analysis/deployment-runs/20260923T180023Z-e8e18e29-floor-graph/`.
Lua, all material streams, explosion bundle and Vortex list remained
unchanged. In a regular `coop_complete_objective` mission on process 18620,
a read-only preflight verified exact bundle SHA, unchanged Lua, active Fire
at hue 240 and a living local player. VFX Swapper was disabled. The user
reported **"nu funkar det!!"** and supplied screenshots showing a uniform
blue fire patch with none of the previously reported warm floor patches.
The single-bundle type-2 RGB-curve change is therefore **visibly confirmed**
as controlling the missing color layer at hue 240 in that context. After the
user selected Fire hue 120 and exploded a new barrel, they also confirmed
that **both the flames and ground surface were green without yellow spots**.
This second final-build observation is a user report, not a second LuaExec
preflight or screenshot. VFX Swapper coexistence with this exact wheel remains
untested. The user subsequently clarified that the mod was tested **as a
client connected to a dedicated server**. Thus the described green/blue
normal-mission visuals cover that client context; no test or claim concerns
running RainbowBarrels code inside the dedicated-server process itself.

Before that further resource inspection, the user disabled **Fire barrels: Custom** and supplied two screenshots
showing stock yellow/orange fire from fresh fires. A post-hoc read-only
LuaExec snapshot on the same process (PID 5860) observed RainbowBarrels still
enabled, Fire disabled, hue 240 retained and the game back in the hub. The
snapshot is later than the screenshots, so the images provide the visual
off-state evidence; no new transient barrel log was recorded for them. This
supports the setting's new-fire isolation without claiming a separate
non-barrel `prop_fire` context was identified in either screenshot.

### RC installer and RainbowFlame coexistence

The user requested a RainbowFlame-style installer and private, unsigned
0.1.0-rc.1 candidate. `resource/build_release_payload.py` packages only
custom resource records and 1,098 authored material streams, never entire
stock bundles. The .NET 10 installer authenticates the exact two stock
bundles and the game's installed decoder, rebuilds the game-tested output
hashes, and journals installation, repair and uninstall. Disposable synthetic
stock fixtures passed install/repair/uninstall, deliberate interruption and
rollback; read-only native Oodle decoding of an unrelated pristine stock
bundle matched independent Python output. The real RC installer has **not**
yet been tested against pristine copies of both target game bundles.

`resource/check_rainbowflame_compatibility.py` compared the exact 1.2.0
RainbowFlame release manifest (172 targets) and RainbowBarrels' 1,104 target
files: **zero shared paths**; both name Darktide Steam build `24735202` and
executable `1.3.770.210`. The RainbowFlame `World.create_particles` hook
selects only Soulblaze/staff/flamer impact names and forwards other effect
names to the original. RainbowBarrels selects barrel and matched `prop_fire`
names and preserves the hook-chain return. This supports file and selector
coexistence but does not replace a live joint-mod test. RainbowFlame is not
currently present in the user's installed `/mods` directory or its installer
receipt directory; it must be installed separately to run the joint test.

The current RainbowBarrels game copy remains the manually staged development
version. `resource/preview_rc_migration.py` passed read-only verification of
eleven development receipts in their exact reverse order: two target bundles
would reach pinned stock hashes `9086f577...` and `775762aa...`; all 1,098
owned custom streams and its mod folder would be removed, while every other
Vortex line is preserved. A unique 1,105-file/51,628,950-byte SHA-256
snapshot was taken under
`analysis/deployment-runs/20260923T191409Z-1ef8c587-rc-migration-snapshot/`,
manifest SHA-256
`4c2de84586eff9f01bc46e2189270f2d4eb38f649e91481ee55b300631c952ca`.
The snapshot and preview **did not change the game**. Applying the rollback
and installing either RC or RainbowFlame still require Darktide closed and
their own explicit authorization.

## Remaining work

1. Check a barrel fire with VFX Swapper enabled at its stock setting and a
   separate, unrelated `prop_fire` if a normal mission provides one.
2. Re-test both barrel types, a normal grenade,
   setting changes, disable/re-enable and mission exit before a completion
   claim. Verify that orange visual layers are not left in either explosion.
3. Build a user-facing installer and authenticated delta payload from the
   tested build, with independent backups, installed-file ownership and rollback.
   Do not distribute complete extracted game resources.
