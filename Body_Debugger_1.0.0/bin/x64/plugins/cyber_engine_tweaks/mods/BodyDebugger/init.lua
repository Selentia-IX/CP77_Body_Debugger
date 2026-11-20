-- Body Debugger: writes what V's body is made of right now to body_debug_runtime.log (in this folder).
-- The scanner (body_debug_scan) reads this log together with your mod folder.

local LOG = "body_debug_runtime.log"
local status = "Load a save, then press Write log."

local function try(fn, fallback)
    local ok, v = pcall(fn)
    if ok and v ~= nil then return tostring(v) end
    return fallback or "?"
end

local function writeLog()
    local player = Game.GetPlayer()
    if not player then
        status = "No player yet. Load a save first."
        return
    end
    if not BodyDebugger then
        status = "Script part not loaded. Check that Codeware is installed and r6\\scripts\\BodyDebugger exists."
        return
    end
    local f = io.open(LOG, "w")
    if not f then
        status = "Could not write " .. LOG
        return
    end
    f:write("# Body Debugger runtime log\n")
    f:write("tool\t" .. BodyDebugger.Version() .. "\n")
    f:write("time\t" .. try(function() return os.date("%Y-%m-%d %H:%M:%S") end) .. "\n")
    f:write("cet\t" .. try(GetVersion) .. "\n")
    f:write("archivexl\t" .. try(function() return ArchiveXL.Version() end) .. "\n")
    f:write("codeware\t" .. try(function() return Codeware.Version() end) .. "\n")
    f:write("bodytype\t" .. try(function() return BodyDebugger.BodyType(player) end) .. "\n")
    f:write("gender\t" .. try(function() return player:GetResolvedGenderName().value end) .. "\n")
    -- class, component, on/off, resource hash, mesh appearance, chunk mask
    local lines = BodyDebugger.Components(player)
    local n = 0
    for _, line in ipairs(lines) do
        if line:sub(1, 1) == "#" then
            f:write("diag\t" .. line:sub(2) .. "\n")
        else
            f:write("comp\t" .. line .. "\n")
            n = n + 1
        end
    end
    f:close()
    status = "Wrote " .. n .. " components to " .. LOG
    print("[BodyDebugger] " .. status)
end

registerHotkey("BodyDebuggerWrite", "Write body debug log", writeLog)

local overlayOpen = false
registerForEvent("onOverlayOpen", function() overlayOpen = true end)
registerForEvent("onOverlayClose", function() overlayOpen = false end)

registerForEvent("onDraw", function()
    if not overlayOpen then return end
    if ImGui.Begin("Body Debugger") then
        if ImGui.Button("Write log") then writeLog() end
        ImGui.Text(status)
    end
    ImGui.End()
end)
