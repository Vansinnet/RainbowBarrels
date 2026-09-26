---@class RainbowBarrelsMod : DMFMod
local mod = get_mod("RainbowBarrels")
local Explosion = require("scripts/utilities/attack/explosion")
local redirects = mod:io_dofile("RainbowBarrels/scripts/mods/RainbowBarrels/redirects")

local prefix = "content/fx/particles/rainbow_barrels/"
local hue_parameter = "rainbow_barrels_hue"
local ground_filled_prefix = prefix .. "fire_lingering_filled_hue_"
local ground_rim_prefix = prefix .. "fire_lingering_rim_hue_"
local stock_ground_filled = "content/fx/particles/liquid_area/fire_lingering"
local ground_window = 4
local ground_radius_squared = 81
local profiles = {
    explosive = {
        template = "explosive_barrel",
        original = "content/fx/particles/explosions/frag_grenade_01",
        clouds = {
            "RainbowBarrels_explosive_00",
            "RainbowBarrels_explosive_02",
            "RainbowBarrels_explosive_09",
        },
    },
    fire = {
        template = "fire_barrel",
        original = "content/fx/particles/destructibles/explosive_barrel_explosion",
        clouds = {
            "RainbowBarrels_fire_01",
            "RainbowBarrels_fire_02",
            "RainbowBarrels_fire_05",
            "RainbowBarrels_fire_06",
            "RainbowBarrels_fire_07",
            "RainbowBarrels_fire_08",
            "RainbowBarrels_fire_09",
            "RainbowBarrels_fire_10",
            "RainbowBarrels_fire_11",
            "RainbowBarrels_fire_12",
            "RainbowBarrels_fire_13",
            "RainbowBarrels_fire_14",
            "RainbowBarrels_fire_16",
            "RainbowBarrels_fire_17",
        },
    },
}

local enabled = false
local resources_ready = false
local selected = {}
local hues = {}
local selected_ground_filled
local selected_ground_rim
local templates = {}
local recent_fire = {}
local ground_owners = setmetatable({}, { __mode = "k" })
local active_ground_fill

local function remember_fire(position)
    local now = Managers.time:time("gameplay")
    for i = #recent_fire, 1, -1 do
        if now - recent_fire[i].time > ground_window then
            table.remove(recent_fire, i)
        end
    end
    recent_fire[#recent_fire + 1] = { position = Vector3Box(position), time = now }
    if #recent_fire > 4 then
        table.remove(recent_fire, 1)
    end
end

local function match_ground(self, unit, extension_init_data)
    if not enabled or DEDICATED_SERVER or not selected.fire or
        extension_init_data.template.name ~= "prop_fire" then
        return
    end
    local now = Managers.time:time("gameplay")
    local position = Unit.world_position(unit, 1)
    local best_index
    local best_distance = ground_radius_squared
    for i = #recent_fire, 1, -1 do
        local entry = recent_fire[i]
        local age = now - entry.time
        if age > ground_window then
            table.remove(recent_fire, i)
        elseif age >= 0 then
            local distance = Vector3.distance_squared(position, entry.position:unbox())
            if distance <= best_distance then
                best_index = i
                best_distance = distance
            end
        end
    end
    if best_index then
        table.remove(recent_fire, best_index)
        ground_owners[self] = selected_ground_filled
        self._vfx_name_filled = selected_ground_filled
        self._vfx_name_rim = selected_ground_rim
    end
end

local function fill_ground(func, self, real_index, ...)
    if not enabled or not selected.fire or not ground_owners[self] then
        return func(self, real_index, ...)
    end
    local previous = active_ground_fill
    active_ground_fill = self
    local ok, result = pcall(func, self, real_index, ...)
    active_ground_fill = previous
    if not ok then
        error(result, 0)
    end
    return result
end

local function update_settings()
    for kind in pairs(profiles) do
        local hue = math.floor(mod:get(kind .. "_hue"))
        hues[kind] = hue / 360
        selected[kind] = mod:get(kind .. "_enabled") and
            prefix .. kind .. "_hue_" .. string.format("%03d", hue) or nil
    end
    local ground_hue = string.format("%03d", math.floor(mod:get("fire_hue")))
    selected_ground_filled = selected.fire and ground_filled_prefix .. ground_hue or nil
    selected_ground_rim = selected.fire and ground_rim_prefix .. ground_hue or nil
    table.clear(templates)
    table.clear(recent_fire)
end

mod:hook(Explosion, "create_husk_explosion", function(func, world, physics_world, wwise_world,
                                                     attacking_owner_unit_or_nil, explosion_template,
                                                     position, rotation, radius_variables, charge_level)
    if enabled and not DEDICATED_SERVER then
        for kind, profile in pairs(profiles) do
            local effect = selected[kind]
            if effect and explosion_template.name == profile.template then
                local vfx = explosion_template.vfx
                if vfx and #vfx == 1 and vfx[1] == profile.original then
                    if kind == "fire" then
                        remember_fire(position)
                    end
                    local cached = templates[explosion_template]
                    if not cached then
                        cached = table.shallow_copy(explosion_template)
                        cached.vfx = { effect }
                        templates[explosion_template] = cached
                    end
                    explosion_template = cached
                end
                break
            end
        end
    end
    return func(world, physics_world, wwise_world, attacking_owner_unit_or_nil,
                explosion_template, position, rotation, radius_variables, charge_level)
end)

mod:hook_require("scripts/extension_systems/liquid_area/husk_liquid_area_extension", function(HuskLiquidAreaExtension)
    mod:hook_safe(HuskLiquidAreaExtension, "init", function(self, extension_init_context, unit,
                                                           extension_init_data, game_session, game_object_id)
        match_ground(self, unit, extension_init_data)
    end)
    mod:hook(HuskLiquidAreaExtension, "_set_liquid_filled", fill_ground)
end)

mod:hook_require("scripts/extension_systems/liquid_area/liquid_area_extension", function(LiquidAreaExtension)
    mod:hook_safe(LiquidAreaExtension, "init", function(self, extension_init_context, unit,
                                                       extension_init_data, game_object_data)
        match_ground(self, unit, extension_init_data)
    end)
    mod:hook(LiquidAreaExtension, "_set_filled", fill_ground)
end)

mod:hook("World", "create_particles", function(func, world, effect_name, position, rotation, scale, particle_group)
    if enabled and active_ground_fill and selected.fire and effect_name == stock_ground_filled and
        world == active_ground_fill._world then
        effect_name = ground_owners[active_ground_fill] or effect_name
    end
    local particle_id = func(world, effect_name, position, rotation, scale, particle_group)
    if enabled and particle_id and not DEDICATED_SERVER then
        local kind = effect_name == selected.explosive and "explosive" or
            effect_name == selected.fire and "fire" or nil
        if kind then
            local clouds = profiles[kind].clouds
            for i = 1, #clouds do
                World.set_particles_material_scalar(world, particle_id, clouds[i], hue_parameter, hues[kind])
            end
        end
    end
    return particle_id
end)

mod.on_enabled = function()
    update_settings()
    enabled = resources_ready
end

mod.on_all_mods_loaded = function()
    resources_ready = redirects and redirects.commit() or false
    if resources_ready and mod:is_enabled() then
        update_settings()
        enabled = true
    end
end

mod.on_disabled = function()
    enabled = false
    table.clear(templates)
    table.clear(recent_fire)
    table.clear(ground_owners)
    active_ground_fill = nil
end

mod.on_unload = function()
    enabled = false
    table.clear(templates)
    table.clear(recent_fire)
    table.clear(ground_owners)
    active_ground_fill = nil
    if redirects then
        redirects.clear()
    end
end

mod.on_setting_changed = function()
    if enabled then
        update_settings()
    end
end

mod.on_game_state_changed = function(status, state_name)
    if status == "exit" and state_name == "StateGameplay" then
        table.clear(templates)
        table.clear(recent_fire)
        table.clear(ground_owners)
        active_ground_fill = nil
    end
end
