"""Body Debugger scanner: which mods change V's body, which one wins each conflict, and what is actually rendered.

Usage:  python body_debug_scan.py ["<game folder>"]
        (or run "Run Body Debugger scan.bat"; with no folder it tries the script's own location, then the default
        Steam, GOG and Epic folders)

Reads the game's own archives, every mod archive and .xl file, and (if present) the in-game log written by the
Body Debugger CET mod (bin/x64/plugins/cyber_engine_tweaks/mods/BodyDebugger/body_debug_runtime.log).
Writes body_debug_report.txt next to this script. Changes nothing in the game folder.
"""
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cp_archive  # noqa: E402
from cp_archive import Archive, fnv1a64  # noqa: E402
from cr2w_dump import CR2W  # noqa: E402

VERSION = "1.0.0"
DEFAULT_GAME_DIRS = [Path(p) for p in (r"C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077",
                                      r"C:\Program Files (x86)\GOG Galaxy\Games\Cyberpunk 2077",
                                      r"C:\Program Files\Epic Games\Cyberpunk2077")]
B = "\\"
CC_FILES = [
    r"base\gameplay\gui\fullscreen\main_menu\female_cco.inkcharcustomization",
    r"base\gameplay\gui\fullscreen\main_menu\male_cco.inkcharcustomization",
    r"ep1\gameplay\gui\fullscreen\main_menu\female_cco_ep1.inkcharcustomization",
    r"ep1\gameplay\gui\fullscreen\main_menu\male_cco_ep1.inkcharcustomization",
]
# paths that count as "V's body" for the conflict list
BODY_KEYS = ("player_base_bodies", "player_base_heads", r"cyberware\player", r"common\skin", r"main_menu" + B,
             "player_female_average", "player_male_average", "player_man_average", "player_woman_average")
PATH_RE = re.compile(rb"(?:base|ep1|engine|mod|user)\\[\x21-\x7e]{2,240}?\.[a-z0-9_]{2,20}(?![a-z0-9_])", re.I)


def find_game(arg):
    for p in ([Path(arg)] if arg else []) + [HERE, *HERE.parents, *DEFAULT_GAME_DIRS]:
        if (p / "bin" / "x64" / "Cyberpunk2077.exe").exists():
            return p
    sys.exit("Game folder not found. Run: python body_debug_scan.py \"<your Cyberpunk 2077 folder>\"")


def paths_in(data):
    return {m.decode("latin-1").lower() for m in PATH_RE.findall(data)}


def first_segment(arc, h):
    """Main CR2W segment only (imports, names), without the buffers: cheap even for big textures."""
    seg_start, seg_end = arc.files[h]
    if seg_start == seg_end:
        return b""
    offset, zsize, size = arc.segments[seg_start]
    arc.f.seek(offset)
    blob = arc.f.read(zsize)
    if zsize == size:
        return blob
    if blob[:4] == b"KARK":
        return cp_archive.oodle_decompress(blob[8:], int.from_bytes(blob[4:8], "little"))
    return cp_archive.oodle_decompress(blob, size)


# --- tiny YAML subset reader for .xl files (mappings, block lists, [flow, lists]) ------------------------------
def parse_yaml(text):
    # shortcut: covers how .xl files are written in practice; anchors, multi-line strings and flow maps are kept as text
    lines = []
    for raw in text.splitlines():
        s = raw.split(" #")[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if s.strip():
            lines.append((len(s) - len(s.lstrip()), s.strip()))

    def scalar(v):
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            return v[1:-1]
        if v.startswith("[") and v.endswith("]"):
            return [scalar(x) for x in v[1:-1].split(",") if x.strip()]
        return v

    def block(i, indent):
        if i < len(lines) and lines[i][1].startswith("- "):
            out = []
            while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("- "):
                out.append(scalar(lines[i][1][2:]))
                i += 1
            return out, i
        out = {}
        while i < len(lines) and lines[i][0] == indent:
            key, _, val = lines[i][1].partition(":")
            key = scalar(key)
            i += 1
            if val.strip():
                out[key] = scalar(val)
            elif i < len(lines) and lines[i][0] > indent:
                out[key], i = block(i, lines[i][0])
            elif i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("- "):
                out[key], i = block(i, indent)
            else:
                out[key] = None
        return out, i

    return block(0, lines[0][0])[0] if lines else {}


def mark(msg):
    """'!!' for problems, '--' for notes that are usually intended."""
    info = ("on purpose", "added by an ArchiveXL patch", "hidden pieces", "check in game")
    return ("    -- " if any(s in msg for s in info) else "    !! ") + msg


def norm(p):
    return str(p).strip().lower().replace("/", B)


# --- scan ------------------------------------------------------------------------------------------------------
def main():
    t0 = time.time()
    game = find_game(sys.argv[1] if len(sys.argv) > 1 else None)
    cp_archive.GAME_BIN = game / "bin" / "x64"
    print(f"Game folder: {game}")

    vanilla = [Archive(p) for d in ("content", "ep1") for p in sorted((game / "archive" / "pc" / d).glob("*.archive"))]
    vhash = {}
    for a in vanilla:
        for h in a.files:
            vhash.setdefault(h, a)
    print(f"Base game: {len(vanilla)} archives, {len(vhash)} files")

    mod_dir = game / "archive" / "pc" / "mod"
    mods = [Archive(p) for p in sorted(mod_dir.glob("*.archive"), key=lambda p: p.name.lower())]
    redmods = [Archive(p) for p in sorted((game / "mods").glob("*/archives/*.archive"), key=lambda p: str(p).lower())]
    # framework archives (ArchiveXL's bundle and similar) load after the mods
    frameworks = [Archive(p) for p in sorted((game / "red4ext" / "plugins").rglob("*.archive"),
                                             key=lambda p: str(p).lower())]
    order = mods + redmods + frameworks
    owners = {}
    for a in order:
        for h in a.files:
            owners.setdefault(h, []).append(a)
    print(f"Mods: {len(mods)} archives in archive\\pc\\mod, {len(redmods)} REDmod, {len(frameworks)} framework")

    # names: base game character creator -> .app files -> meshes; plus every path any mod file or .xl mentions
    names = set()
    for path in CC_FILES:
        h = fnv1a64(path)
        if h in vhash:
            names.add(path)
            names |= paths_in(vhash[h].read(h))
    for path in [n for n in names if n.endswith((".app", ".ent"))]:
        h = fnv1a64(path)
        if h in vhash:
            names |= paths_in(vhash[h].read(h))
    for a in order:
        for h in a.files:
            try:
                names |= paths_in(first_segment(a, h))
            except Exception:
                pass
    xls = sorted(mod_dir.glob("*.xl"), key=lambda p: p.name.lower()) + sorted((game / "mods").glob("*/archives/*.xl"))
    xl_data = {}
    for x in xls:
        text = x.read_text("utf-8", "replace")
        names |= paths_in(text.encode("latin-1", "replace"))
        try:
            xl_data[x] = parse_yaml(text)
        except Exception as e:  # report, don't stop
            xl_data[x] = {"_error": str(e)}
    name_of = {fnv1a64(n): n for n in names}

    def label(h):
        return name_of.get(h, f"<unknown path, hash {h}>")

    # .xl: material name fixes and appearance patches per target path
    fixes, app_patches, xl_touch = {}, {}, {}
    for x, d in xl_data.items():
        res = d.get("resource") if isinstance(d, dict) else None
        res = res if isinstance(res, dict) else {}
        for target, spec in (res.get("fix") or {}).items() if isinstance(res.get("fix"), dict) else []:
            if isinstance(spec, dict) and isinstance(spec.get("names"), dict):
                fixes.setdefault(norm(target), {}).update({k: v for k, v in spec["names"].items()})
            xl_touch.setdefault(x, set()).add(norm(target))
        for src, spec in (res.get("patch") or {}).items() if isinstance(res.get("patch"), dict) else []:
            targets = spec.get("targets", []) if isinstance(spec, dict) else spec if isinstance(spec, list) else []
            props = spec.get("props", []) if isinstance(spec, dict) else []
            for t in targets or []:
                xl_touch.setdefault(x, set()).add(norm(t))
                if "appearances" in (props or []):
                    app_patches.setdefault(norm(t), []).append(norm(src))
            xl_touch.setdefault(x, set()).add(norm(src))

    def winner(h):
        """(archive that serves this hash, list of all mod archives that ship it)."""
        own = owners.get(h, [])
        return (own[0] if own else vhash.get(h)), own

    def src_name(a):
        if a is None:
            return ("not in any archive file the scan reads (created or redirected while the game runs, "
                    "for example by ArchiveXL or a script mod)")
        return ("base game: " if a in vanilla else "framework: " if a in frameworks else "") + Path(a.path).name

    def mesh_check(path, appearance=None, mask=None):
        """Problems with the mesh that is served at this path, for the given appearance."""
        h = fnv1a64(path)
        a, _ = winner(h)
        if a is None:
            return ["mesh file not found in any archive: nothing can be drawn"]
        try:
            cr = CR2W(a.read(h))
            mesh = cr.dump({"CMesh"})[0]["props"]
        except Exception as e:
            return [f"could not read mesh ({e})"]
        mats = {m.get("name") for m in mesh.get("materialEntries", []) if isinstance(m, dict)}
        ex = {e["export"]: e["props"] for e in cr.dump({"meshMeshAppearance"})}
        apps = {}
        for ref in mesh.get("appearances", []):
            p = ex.get(int(str(ref)[1:])) if str(ref).startswith("#") else None
            if p:
                apps[p.get("name")] = p.get("chunkMaterials", [])
        patched = set()
        for src in app_patches.get(path, []):
            try:
                pa, _ = winner(fnv1a64(src))
                pcr = CR2W(pa.read(fnv1a64(src)))
                patched |= {e["props"].get("name") for e in pcr.dump({"meshMeshAppearance"})}
            except Exception:
                pass
        ren = fixes.get(path, {})
        out = []
        first = next(iter(apps), None)
        if appearance and appearance not in ("None", "default", "") and appearance not in apps:
            if appearance in patched:
                out.append(f"look '{appearance}' is added by an ArchiveXL patch (not checked further)")
                return out
            if "player_base_heads" in path:  # heads, eyes, brows: character creator extensions add looks at runtime
                out.append(f"look '{appearance}' is not in the mesh file; ArchiveXL character creator extensions "
                           f"can add it at runtime, so check in game (not checked further)")
                return out
            out.append(f"look '{appearance}' NOT in this mesh: the game uses its first look "
                       f"'{first or '(unnamed)'}' instead (wrong skin tone or style)")
            appearance = first
        check = [appearance] if appearance in apps else list(apps)
        for app in check:
            shown = app if app not in (None, "None", "") else "(unnamed)"
            used = apps.get(app, [])
            bad = sorted({c for c in used if c not in mats and ren.get(c) not in mats and c != "none"})
            if bad:
                out.append(f"look '{shown}' uses materials the mesh doesn't have: {', '.join(bad)} "
                           f"-> those pieces are INVISIBLE")
            if "none" in used and "none" not in mats:
                out.append(f"look '{shown}' hides {used.count('none')} of {len(used)} pieces on purpose "
                           f"(material 'none')")
        if mask is not None:
            chunks = len(apps.get(appearance) or apps.get(first) or [])
            hidden = [i for i in range(chunks) if not (mask >> i) & 1]
            if hidden:
                out.append(f"hidden pieces (chunk mask): {hidden} of {chunks}")
        return out

    # --- report ---------------------------------------------------------------------------------------------
    rep = [f"Body Debugger report {VERSION}  ({time.strftime('%Y-%m-%d %H:%M')})", f"Game: {game}", ""]
    if (mod_dir / "modlist.txt").exists():
        rep += ["NOTE: archive\\pc\\mod\\modlist.txt exists, so the real load order may differ from the alphabetical "
                "order used below.", ""]
    rep += ["How to read this: archives load in alphabetical order and the FIRST one that has a file wins. Base game "
            "files are used only when no mod ships that path.", ""]

    runtime = next((game / "bin/x64/plugins/cyber_engine_tweaks/mods").glob("BodyDebugger/body_debug_runtime.log"),
                   None)
    rep.append("=" * 100)
    rep.append("1. WHAT V IS WEARING AS A BODY RIGHT NOW (from the in-game log)")
    rep.append("=" * 100)
    if not runtime:
        rep += ["No in-game log found. In game: open the CET overlay, press 'Write log' in the Body Debugger window "
                "(or bind its hotkey), then run this scan again.", ""]
    else:
        rep.append(f"Log: {runtime}  (written {time.strftime('%Y-%m-%d %H:%M', time.localtime(runtime.stat().st_mtime))})")
        for line in runtime.read_text("utf-8", "replace").splitlines():
            f = line.split("\t")
            if f[0] in ("tool", "time", "cet", "archivexl", "codeware", "bodytype", "gender", "diag"):
                rep.append(f"  {f[0]}: {f[1] if len(f) > 1 else ''}")
        rep.append("")
        last_owner = None
        for line in runtime.read_text("utf-8", "replace").splitlines():
            f = line.split("\t")
            if f[0] != "comp" or len(f) < 8:
                continue
            _, owner, cls, comp, on, h, app, mask = f[:8]
            h = int(h)
            if h == 0:
                continue
            path = label(h)
            body = any(k in path for k in BODY_KEYS) or not path.startswith("<")
            a, own = winner(h)
            if a in vanilla and (not body or on == "off"):  # unchanged base game pieces that aren't drawn: noise
                continue
            if owner != last_owner:
                rep += ["", f"[{owner}]"]
                last_owner = owner
            rep.append(f"- {comp}  [{cls}, {on}]")
            rep.append(f"    file:  {path}")
            rep.append(f"    look:  {app}")
            rep.append(f"    from:  {src_name(a)}")
            if len(own) > 1:
                rep.append(f"    also shipped by (ignored): {', '.join(Path(x.path).name for x in own[1:])}")
            if own and h in vhash:
                rep.append("    (replaces the base game file)")
            mesh_path = path if path.endswith(".mesh") else None
            if path.endswith(".morphtarget") and a is not None:
                try:
                    mesh_path = next((norm(i) for i in CR2W(a.read(h)).imports if i.endswith(".mesh")), None)
                    rep.append(f"    morph target's mesh: {mesh_path}  (from {src_name(winner(fnv1a64(mesh_path))[0])})")
                except Exception:
                    pass
            if mesh_path:
                for p in mesh_check(mesh_path, app, int(mask, 16)):
                    rep.append(mark(p))
            elif path.startswith("<"):
                rep.append("    (file name unknown; 'from' shows which archive has it)")
        rep.append("")

    rep.append("=" * 100)
    rep.append("2. BODY FILES CHANGED BY MODS, AND CONFLICTS")
    rep.append("=" * 100)
    body_hashes = sorted({h for h in owners if any(k in label(h) for k in BODY_KEYS)}, key=label)
    for h in body_hashes:
        own = owners[h]
        tag = "CONFLICT" if len(own) > 1 else "changed"
        base = "replaces base game file" if h in vhash else "new file"
        rep.append(f"[{tag}] {label(h)}  ({base})")
        rep.append(f"    used:    {Path(own[0].path).name}")
        for x in own[1:]:
            rep.append(f"    ignored: {Path(x.path).name}")
        if label(h).endswith(".mesh"):
            for p in mesh_check(label(h)):
                rep.append(mark(p))
    if not body_hashes:
        rep.append("No mod ships a known body, head or skin file.")
    rep.append("")

    rep.append("=" * 100)
    rep.append("3. ARCHIVEXL CONFIGS (.xl) THAT TOUCH BODY FILES")
    rep.append("=" * 100)
    for x, d in xl_data.items():
        touched = sorted(p for p in xl_touch.get(x, ()) if any(k in p for k in BODY_KEYS))
        err = d.get("_error") if isinstance(d, dict) else None
        if touched or err:
            rep.append(f"{x.name}")
            if err:
                rep.append(f"    could not read: {err}")
            for p in touched:
                rep.append(f"    {p}")
    rep.append("")

    rep.append("=" * 100)
    rep.append("4. ALL MOD ARCHIVES (load order)")
    rep.append("=" * 100)
    for i, a in enumerate(order, 1):
        n_body = sum(1 for h in a.files if h in set(body_hashes))
        n_vanilla = sum(1 for h in a.files if h in vhash)
        rep.append(f"{i:4}. {Path(a.path).relative_to(game)}  files {len(a.files)}, replaces base game {n_vanilla}, "
                   f"body {n_body}")
    rep += ["", f"Scan took {time.time() - t0:.0f} s."]

    out = HERE / "body_debug_report.txt"
    out.write_text("\n".join(rep) + "\n", "utf-8")
    print(f"Report written: {out}")


if __name__ == "__main__":
    main()
