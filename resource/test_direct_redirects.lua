local mod = {}
local registrations = {}
local cleared = false
local refuse
local fake = {
    register = function(_, spec)
        registrations[#registrations + 1] = spec
        return #registrations
    end,
    commit = function() end,
    state = function(index)
        return index == refuse and "refused" or "active"
    end,
    clear = function()
        cleared = true
    end,
}

function mod:io_dofile(path)
    if path:match("/asset_redirect$") then
        return fake
    end
    return dofile("scripts/mods/RainbowBarrels/redirect_files.lua")
end
function mod:info() end
function mod:echo() end

function get_mod()
    return mod
end

local redirects = dofile("scripts/mods/RainbowBarrels/redirects.lua")
assert(#registrations == 1100)
assert(registrations[1].stock == "98bb14b1d247a0c8" and not registrations[1].virtual)
assert(registrations[2].stock == "b224998193576995" and not registrations[2].virtual)
for i = 3, #registrations do
    assert(registrations[i].virtual == true)
    assert(registrations[i].stock:match("^data/rb/%x%x%x%x%x%x%x%x%x%x%x%x%x%x%x%x$"))
end
assert(redirects.commit() == true)
refuse = 3
assert(redirects.commit() == false)
redirects.clear()
assert(cleared)
print("1100 registrations and all-or-nothing redirect readiness passed")
