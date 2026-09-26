local mod = get_mod("RainbowBarrels")
local reforge = mod:io_dofile("RainbowBarrels/scripts/mods/RainbowBarrels/reforge")

if not reforge then
    mod:error("RainbowBarrels could not load Reforge; stock effects will be used.")
    return nil
end

-- Two authored effect bundles replace stock bundles (pinned by SHA-256) and
-- 1,098 material streams are served at new bundle/data/rb/ paths. Edit
-- reforge.json and run `reforge build` to change this list.
local manifest = "RainbowBarrels/scripts/mods/RainbowBarrels/reforge_manifest"
local handles = reforge.register_manifest(mod, manifest)

return {
    commit = function()
        reforge.commit()
        local ready = 0
        local restart = false
        for i = 1, #handles do
            local handle = handles[i]
            local state = reforge.state(handle)
            if reforge.served(state) then
                ready = ready + 1
            elseif state == "restart_required" then
                restart = true
            else
                mod:info("resource %s not served: %s %s", handle.stock, state, reforge.reason(handle) or "")
            end
        end
        mod:info("resource redirects served: %d of %d", ready, #handles)
        if restart then
            mod:echo("RainbowBarrels: restart Darktide to apply resource redirects.")
        elseif #handles == 0 or ready ~= #handles then
            mod:echo("RainbowBarrels: resource redirects incomplete (%d/%d); stock effects remain active. Check the log or /reforge.", ready, #handles)
        end
        return #handles > 0 and ready == #handles
    end,
    clear = function()
        reforge.clear(mod)
    end,
}
