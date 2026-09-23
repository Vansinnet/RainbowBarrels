return {
    run = function()
        fassert(rawget(_G, "new_mod"), "`RainbowBarrels` failed loading DMF.")
        new_mod("RainbowBarrels", {
            mod_script = "RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels",
            mod_data = "RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels_data",
            mod_localization = "RainbowBarrels/scripts/mods/RainbowBarrels/RainbowBarrels_localization",
        })
    end,
    packages = {},
}
