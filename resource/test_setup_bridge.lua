local fixture_root = "scripts/mods/RainbowBarrels/setup.lua"
local function fixture()
    local state, files, launches, messages = {}, {}, {}, {}
    local executable = true
    local mod = {}
    function mod:persistent_table() return state end
    function mod:echo(_, text) messages[#messages + 1] = text end
    local env = setmetatable({ get_mod = function() return mod end }, { __index = _G })
    env._G = env
    env.Mods = { lua = {
        io = { open = function(path)
            if path:match("%.exe$") then
                return executable and { close = function() end } or nil
            end
            local text = files[path]
            if text then
                return { read = function(_, count) return text:sub(1, count) end, close = function() end }
            end
        end },
        os = { execute = function(command) launches[#launches + 1] = command return true end },
    } }
    local function load() return assert(loadfile(fixture_root, "t", env))() end
    local function status(code)
        files["../mods/RainbowBarrels/setup-status-" .. state.token .. ".txt"] = code .. "\nmessage\n"
    end
    return load, state, launches, status, function() executable = false end, env, files
end

local load, state, launches, status = fixture()
local setup = load()
setup.start()
assert(#launches == 1 and #state.token == 32 and state.token:match("^%x+$"))
assert(not setup.poll(1))
status("waiting")
assert(not setup.poll(1))
local reloaded = load()
reloaded.start()
assert(#launches == 1, "Hot reload must not launch duplicate workers")
status("installed")
assert(not reloaded.poll(1), "Installed in this process never implies loaded by this process")

load, state, launches, status = fixture()
setup = load()
setup.start()
status("ready")
assert(setup.poll(1))
setup.request("uninstall")
assert(#launches == 2 and launches[2]:find("%-%-uninstall"))
assert(not setup.poll(1))
status("uninstalled")
assert(not setup.poll(1))

load, state, launches, status = fixture()
setup = load()
setup.start()
assert(not setup.poll(61) and state.status == "error", "Missing helper response must fail closed")
setup.request("retry")
assert(#launches == 2 and state.status == "checking")
status("error")
assert(not setup.poll(1))

local missing
load, state, launches, status, missing = fixture()
missing()
setup = load()
setup.start()
assert(#launches == 0 and not setup.poll(1))

local env, files
load, state, launches, status, missing, env, files = fixture()
local calls = 0
env.math = setmetatable({ random = function()
    calls = calls + 1
    return calls <= 32 and 1 or 2
end }, { __index = math })
files["../mods/RainbowBarrels/setup-status-" .. string.rep("1", 32) .. ".txt"] = "ready\nstale\n"
setup = load()
setup.start()
assert(state.token == string.rep("2", 32) and not setup.poll(1), "Never consume an old process's ready file")
print("Setup bridge passed: startup gating, hot reload, restart requirement, uninstall, error, retry, missing helper, stale session")
