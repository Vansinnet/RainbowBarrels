local mod = get_mod("RainbowBarrels")

return {
    name = mod:localize("mod_name"),
    description = mod:localize("mod_description"),
    is_togglable = true,
    options = {
        widgets = {
            {
                setting_id = "explosive_group",
                type = "group",
                sub_widgets = {
                    { setting_id = "explosive_enabled", type = "checkbox", default_value = true },
                    { setting_id = "explosive_hue", type = "numeric", default_value = 120,
                      range = { 0, 359 }, decimals_number = 0 },
                },
            },
            {
                setting_id = "fire_group",
                type = "group",
                sub_widgets = {
                    { setting_id = "fire_enabled", type = "checkbox", default_value = true },
                    { setting_id = "fire_hue", type = "numeric", default_value = 120,
                      range = { 0, 359 }, decimals_number = 0 },
                },
            },
        },
    },
}
