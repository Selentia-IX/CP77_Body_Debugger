# Body Debugger

Finds out what your V's body is actually made of, and which mod each part comes from.

When a body part is invisible, the wrong skin tone, or has a seam, the cause is usually one of these: two mods ship
the same file and the wrong one wins, a mesh asks for a material it doesn't have, or a look is missing so the game
falls back to another one. Body Debugger checks all of that and writes it to one text report you can read or share.

It has two parts:

- **The in-game logger** (a small CET mod). Press one button and it writes down every visible piece on V right now:
  head, torso, arms, legs, hair, cyberware and clothes, with the look (skin tone, style) each one uses.
- **The scanner** (a script you run outside the game). It reads your mod folder and the game's own files, works out
  which mod each piece comes from, lists body file conflicts, and checks the meshes for problems.

Nothing in your game or your mods is changed. It only reads in game files.

## Requirements

- Cyber Engine Tweaks
- RED4ext
- Codeware
- ArchiveXL
- For the scanner: Python 3.8 or newer ([python.org](https://www.python.org/downloads/)). Nothing else.

## Install

1. **Logger:** copy the `bin` and `r6` folders from the logger download into your game folder (the one with `bin`
   and `archive` in it). Vortex and MO2 can install it like any other mod.
2. **Scanner:** extract the scanner download anywhere, for example your desktop.

## Use

1. Start the game and load a save.
2. Open the CET overlay. In the **Body Debugger** window, press **Write log**. (You can also bind a hotkey for it in
   CET's Hotkeys tab.) It says how many pieces it wrote.
3. Run **Run Body Debugger scan.bat** from the scanner folder. It takes about half a minute and opens
   `body_debug_report.txt` when it's done.

If your game isn't in the default Steam, GOG or Epic folder, either drag your Cyberpunk 2077 folder onto the .bat
file, or put the `Body Debugger Scanner` folder inside your game folder (next to `bin` and `archive`) and run the .bat
from there.

You can run the scanner without step 2. You'll get the conflict list, just not the "what V is wearing" part.

## Reading the report

1. **What V is wearing right now:** every visible piece, its file, its look, and the mod it comes from. Other mods
   that ship the same file but lose are listed as "ignored".
2. **Body files changed by mods, and conflicts:** every body, head, skin and arm file a mod replaces. "CONFLICT"
   means two or more mods ship it; the first one in load order is used.
3. **ArchiveXL configs** that touch body files.
4. **All mod archives** in load order.

Lines marked `!!` are problems:

- *uses materials the mesh doesn't have:* those pieces are invisible.
- *look NOT in this mesh:* the game uses the mesh's first look instead (often the wrong skin tone).

Lines marked `--` are notes that are usually fine, like pieces hidden on purpose by the mod or by clothing.

Some files show as an unknown name with a number. The report still says which archive they come from; the file name
just isn't written anywhere the scanner can read.

## Good to know

- Archives in `archive\pc\mod` load in alphabetical order, and the first one that has a file wins. If you use a
  `modlist.txt` to change the order, the report warns you, because it uses alphabetical order.
- Write the log in the situation where the problem shows, for example after changing your look at the mirror.
- The log file is `body_debug_runtime.log` in `bin\x64\plugins\cyber_engine_tweaks\mods\BodyDebugger`.

## Uninstall

Delete `bin\x64\plugins\cyber_engine_tweaks\mods\BodyDebugger` and `r6\scripts\BodyDebugger`, and the scanner folder.
