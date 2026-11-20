// Body Debugger: lists every mesh component on V, for the CET part to write to a log.
// Needs Codeware (component fields and GetComponents).

public abstract class BodyDebugger {
  public static func Version() -> String = "1.0.0";

  // One tab-separated line per mesh component, on V and on every item attached to V (body parts, hair, clothes):
  // owner, class, component name, enabled, resource hash (decimal), mesh appearance, chunk mask (hex)
  public static func Components(player: ref<GameObject>) -> array<String> {
    let out: array<String>;
    if !IsDefined(player) {
      return out;
    }
    BodyDebugger.AddComponents(out, "player", player);
    ArrayPush(out, "#player components: " + BodyDebugger.Classes(player));
    let ts = GameInstance.GetTransactionSystem(player.GetGame());
    let slots = TweakDBInterface.GetRecords(n"AttachmentSlot_Record");
    if ArraySize(slots) == 0 {
      slots = TweakDBInterface.GetRecords(n"AttachmentSlot");
    }
    let items = 0;
    for rec in slots {
      let slot = rec.GetID();
      let item = ts.GetItemInSlot(player, slot);
      if IsDefined(item) {
        items += 1;
        let owner = BodyDebugger.IdName(slot) + " = " + BodyDebugger.IdName(ItemID.GetTDBID(item.GetItemID()));
        BodyDebugger.AddComponents(out, owner, item);
        ArrayPush(out, "#item " + owner + ": " + BodyDebugger.Classes(item));
      }
    }
    // lines starting with '#' are diagnostics, not components
    ArrayInsert(out, 0, "#slots " + IntToString(ArraySize(slots)) + ", items attached " + IntToString(items));
    return out;
  }

  private static func IdName(id: TweakDBID) -> String {
    let s = TDBID.ToStringDEBUG(id);
    return NotEquals(s, "") ? s : "#" + BodyDebugger.Dec(TDBID.ToNumber(id));
  }

  // every component class on an entity with its count, e.g. "entMeshComponent x3, gameTargetingComponent x1"
  private static func Classes(ent: ref<Entity>) -> String {
    let names: array<String>;
    let counts: array<Int32>;
    for comp in ent.GetComponents() {
      let cls = NameToString(comp.GetClassName());
      let i = ArrayFindFirst(names, cls);
      if i < 0 {
        ArrayPush(names, cls);
        ArrayPush(counts, 1);
      } else {
        counts[i] += 1;
      }
    }
    let s = "";
    let total = 0;
    let i = 0;
    while i < ArraySize(names) {
      s += ", " + names[i] + " x" + IntToString(counts[i]);
      total += counts[i];
      i += 1;
    }
    return IntToString(total) + " total" + s;
  }

  private static func AddComponents(out lines: array<String>, owner: String, ent: ref<Entity>) {
    for comp in ent.GetComponents() {
      let line = BodyDebugger.Describe(comp);
      if NotEquals(line, "") {
        ArrayPush(lines, owner + "\t" + line);
      }
    }
  }

  public static func BodyType(player: ref<GameObject>) -> String {
    return NameToString(ArchiveXL.GetBodyType(player));
  }

  private static func Describe(comp: ref<IComponent>) -> String {
    let cls = NameToString(comp.GetClassName());
    let name = NameToString(comp.name);
    let morph = comp as entMorphTargetSkinnedMeshComponent;
    if IsDefined(morph) {
      return BodyDebugger.Line(cls, name, morph.isEnabled, ResourceAsyncRef.GetHash(morph.morphResource),
        morph.meshAppearance, morph.chunkMask);
    }
    // body parts, hair and clothes on V are skinned meshes (garment and character creator ones extend this)
    let skinned = comp as entSkinnedMeshComponent;
    if IsDefined(skinned) {
      return BodyDebugger.Line(cls, name, skinned.isEnabled, ResourceAsyncRef.GetHash(skinned.mesh),
        skinned.meshAppearance, skinned.chunkMask);
    }
    let mesh = comp as MeshComponent;
    if IsDefined(mesh) {
      return BodyDebugger.Line(cls, name, mesh.isEnabled, ResourceAsyncRef.GetHash(mesh.mesh),
        mesh.meshAppearance, mesh.chunkMask);
    }
    return "";
  }

  private static func Line(cls: String, name: String, enabled: Bool, hash: Uint64, app: CName, mask: Uint64) -> String {
    return cls + "\t" + name + "\t" + (enabled ? "on" : "off") + "\t" + BodyDebugger.Dec(hash) + "\t"
      + NameToString(app) + "\t" + BodyDebugger.Hex(mask);
  }

  // Uint64 as decimal / hex text (done here, not in Lua, so no precision is lost)
  private static func Dec(v: Uint64) -> String {
    if v == 0ul {
      return "0";
    }
    let s = "";
    while v > 0ul {
      s = IntToString(Cast<Int32>(v % 10ul)) + s;
      v = v / 10ul;
    }
    return s;
  }

  private static func Hex(v: Uint64) -> String {
    let digits = "0123456789ABCDEF";
    let s = "";
    let i = 0;
    while i < 16 {
      s = StrMid(digits, Cast<Int32>(v % 16ul), 1) + s;
      v = v / 16ul;
      i += 1;
    }
    return s;
  }
}
