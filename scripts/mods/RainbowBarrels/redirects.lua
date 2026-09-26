local mod = get_mod("RainbowBarrels")
local redirect = mod:io_dofile("RainbowBarrels/scripts/mods/RainbowBarrels/asset_redirect")
local materials = mod:io_dofile("RainbowBarrels/scripts/mods/RainbowBarrels/redirect_files")

if not redirect or not materials then
    mod:error("RainbowBarrels could not load its resource redirects; stock effects will be used.")
    return nil
end

local bundles = {
    { stock = "98bb14b1d247a0c8", sha256 = "9086f577b55278286bc5cd72de529300d61ba15d2612ad66a1cbe8b272d4da48" },
    { stock = "b224998193576995", sha256 = "775762aae54cfd5313856f8b097e2527774600e92df896d375e4af6b8916376d" },
}

local handles = {}
for i = 1, #bundles do
    local bundle = bundles[i]
    handles[#handles + 1] = redirect.register(mod, {
        stock = bundle.stock,
        file = "payload/bundles/" .. bundle.stock,
        sha256 = bundle.sha256,
    })
end
for i = 1, #materials do
    local name = materials[i]
    handles[#handles + 1] = redirect.register(mod, {
        stock = "data/rb/" .. name,
        file = "payload/materials/" .. name,
        virtual = true,
    })
end

local function served(state)
    return state == "active" or state == "shared"
end

return {
    commit = function()
        redirect.commit()
        local ready = 0
        local restart = false
        for i = 1, #handles do
            local state = redirect.state(handles[i])
            if served(state) then
                ready = ready + 1
            elseif state == "restart_required" then
                restart = true
            end
        end
        mod:info("resource redirects served: %d of %d", ready, #handles)
        if ready ~= #handles then
            mod:echo("RainbowBarrels: resource redirects incomplete (%d/%d); stock effects remain active. Check the log.", ready, #handles)
        end
        if restart then
            mod:echo("RainbowBarrels: restart Darktide to apply resource redirects.")
        end
        return ready == #handles
    end,
    clear = function()
        redirect.clear(mod)
    end,
}
