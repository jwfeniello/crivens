"""Grabbed by the Ghoulies scene-script (Script asset) disassembler / assembler.

The format and opcode semantics come from the game's VM in default.xbe:
Scripting::ExecuteScript runs the current instruction through 17 handlers (ScriptHandlers table)
until one claims it. Instruction = u32 size (incl. 8-byte header), u32 opcode, operands.
Handlers return Halted (wait a frame), Completed (next instruction), Skipped (end of a block).

Block structure:
  SetPlayState ... WaitForMoveOn   a "play" (stage of a scene); SetPlayState may skip to its end
  <XxxCondition> ... EndCondition  registers a trigger; the body runs later when it fires

usage:
  python -I ghoul_script.py disasm <descriptor> [out.gscript]
  python -I ghoul_script.py asm <in.gscript> <out_descriptor>
  python -I ghoul_script.py roundtrip <assets_dir>          (byte-exact check of every script)
  python -I ghoul_script.py dumpall <assets_dir> <out_dir>  (write every script as .gscript)
"""
import re
import struct
import sys
from pathlib import Path

# field types: tag = char[64], aid = char[128], sN = char[N], u32, f32, hex (u32 shown in hex),
# u8 (single byte, used by SetPlayerObjParams)
T, A = "tag", "aid"


def rep(n, fields):
    out = []
    for i in range(n):
        out += [(f"{name}{i + 1}", typ) for name, typ in fields]
    return out


SPEC = {
    0x00: ("EndScript", []),
    0x01: ("SetBackground", [("model", A)]),
    0x02: ("AddSceneControl", [("objparams", A)]),
    0x03: ("LoadPackage", [("package", A)]),
    0x04: ("SetSceneFlags", [("flags", "hex")]),
    0x05: ("Op05", [("value", "u32")]),
    0x06: ("SetNumSuperScaryInputs", [("count", "u32")]),
    0x07: ("SetSceneValue07", [("value", "u32")]),
    0x08: ("SetMindFloatByTag", [("tag", T), ("value", "f32")]),
    0x09: ("SetNoAttackTimer", [("tag", T), ("seconds", "f32")]),
    0x0A: ("SetSceneName", [("loctextKey", "s64"), ("showTitle", "u32"), ("fadeTime", "f32"), ("duration", "f32")]),
    0x0B: ("SetPlayerObjParams", [("slot", "u8"), ("objparams", "s131")]),
    0x0E: ("SetPlayState", [("playerControllable", "u32"), ("playType", "u32"), ("description", A),
                            ("requiredState", "u32"), ("skipIfBusy", "u32")]),
    0x0F: ("WaitForMoveOn", []),
    0x10: ("WaitForMoveOnSimple", []),
    0x11: ("MoveOn", []),
    0x12: ("SetActionsEnabled", [("enabled", "u32")]),
    0x13: ("PlayCutscene", [("cutscene", A), ("waitForEnd", "u32"), ("restoreActions", "u32")]),
    0x14: ("ShowDialog", [("speakerTag", T), ("dialog", "s64"), ("randomVariants", "u32"),
                          ("skipIfBusy", "u32"), ("playOnce", "u32"), ("onceSlot", "u32")]),
    0x15: ("PlayMovieClip", [("movie", A), ("param1", "u32"), ("param2", "u32")]),
    0x17: ("PlayEventIntro", [("challengeListId", "u32"), ("param", "u32"), ("exitPrevious", "u32"), ("title", "s64")]),
    0x18: ("EndDescribingChallenge", []),
    0x19: ("CreateKillAllChallenge", []),
    0x1A: ("CreateTimeLimitChallenge", [("seconds", "f32")]),
    0x1B: ("CreateXChallenge", []),
    0x1C: ("CreateKillAllByTagChallenge", [("tag", T), ("flag", "u32")]),
    0x1D: ("CreateKillNByTagChallenge", [("minCount", "u32"), ("maxCount", "u32"), ("tag", T)]),
    0x1E: ("CreateTimedChallenge1E", [("seconds", "f32")]),
    0x1F: ("CreateFindTheGhoulieKeyChallenge", []),
    0x21: ("CreateDontKillByTagChallenge", [("tag", T)]),
    0x22: ("CreateChallenge22", []),
    0x23: ("CreateWeaponsOnlyChallenge", []),
    0x25: ("CreateNextOneDifferentChallenge", rep(5, [("tag", T), ("enabled", "u32")])),
    0x26: ("CreateChallenge26", []),
    0x27: ("CreateFindTheKeyChallenge", [("count", "u32")]),
    0x28: ("CreateNoBreakHouseChallenge", []),
    0x29: ("UpdateDoor", [("doorId", "u32"), ("state", "u32"), ("waitUntilDone", "u32"), ("param", "u32")]),
    0x2A: ("SpawnGhoulyWithBox", [("ghoulybox", A), ("boxId", "u32"), ("actorAttribs", A), ("waitForOpen", "u32")]),
    0x2B: ("ExecuteGhoulyspawn", [("ghoulyspawn", A)]),
    0x2C: ("PlayerAction2C", []),
    0x2D: ("SpawnPlayer", []),
    0x2E: ("PlayerSetState2E", [("value", "u32")]),
    0x2F: ("SetPlayerWorried", []),
    0x30: ("EndPlayerDroneAction", []),
    0x31: ("SetPlayerWeapon", [("objparams", A)]),
    0x32: ("SetVar32", [("value", "u32")]),
    0x33: ("SetVar33", [("value", "u32")]),
    0x34: ("SetVar34ByTag", [("value", "u32"), ("tag", T)]),
    0x35: ("SetVar35", [("value", "u32")]),
    0x36: ("SetVar36ByTag", [("value", "u32"), ("tag", T)]),
    0x37: ("SetVar37", [("value", "f32")]),
    0x38: ("SetVar38", [("value", "u32")]),
    0x3A: ("PlayCutsceneStream", [("soundbank", A)]),
    0x3B: ("StopSound", []),
    0x3C: ("EndCondition", []),
    0x3D: ("TimeoutCondition", [("seconds", "u32"), ("flag", "u32")]),
    0x3E: ("NumberGhouliesAliveCondition", [("count", "u32"), ("delay", "f32")]),
    0x3F: ("ScareSourceProximityCondition", []),
    0x40: ("ObjectPickedUpCondition", [("tag", T), ("delay", "f32")]),
    0x41: ("NumberGhouliesKilledCondition", [("count", "u32"), ("delay", "f32")]),
    0x42: ("NumberOfKnockdownsCondition", [("count", "u32"), ("tag", T), ("delay", "f32")]),
    0x43: ("PlayerApproachesDoorCondition", [("doorId", "u32"), ("minDistance", "f32")]),
    0x44: ("HauntedObjectActivatedCondition", [("tag", T)]),
    0x45: ("StartChallengeMusic", []),
    0x46: ("ResetPlayerWeapon", []),
    0x47: ("PlayerEntersRegionCondition", [("region", "u32")]),
    0x48: ("PlayerLeavesRegionCondition", [("region", "u32")]),
    0x49: ("SetGlobalFlags", [("mask", "hex")]),
    0x4A: ("ClearGlobalFlags", [("mask", "hex")]),
    0x4B: ("SetLighting", [("colour1", "hex"), ("intensity", "f32"), ("enable", "u32"), ("start1", "f32"),
                       ("end1", "f32"), ("param", "f32"), ("start2", "f32"), ("end2", "f32"), ("colour2", "hex")]),
    0x4C: ("Op4C", [("value", "u32")]),
    0x4E: ("RandomEvent", [("param", "u32"), ("event", "u32"), ("chancePercent", "f32")]),
    0x4F: ("SetDoorInitialState", [("doorId", "u32"), ("state", "u32")]),
    0x50: ("CreateRandomTagChallenge", rep(5, [("tag", T), ("enabled", "u32")]) + [("flag", "u32")]),
    0x51: ("ActivateObjectsByTag", [("tag", T), ("instanceId", "u32")]),
    0x52: ("Op52", [("name", A)]),
    0x53: ("PlayWalkinCutscene", [("cutscene", A)]),
    0x55: ("PlayMusicByActorTag", [("tag", T)]),
    0x56: ("Op56", [("value", "u32")]),
    0x57: ("PlayRoomAmbience", [("soundbank", A)]),
    0x58: ("SetActorStrategyByTag", [("tag", T), ("strategy", "s64")]),
    0x59: ("SendMessageToTag", [("tag", T)]),
    0x5A: ("SpecificGhouliesAliveCondition", [("count", "u32"), ("tag", T), ("delay", "f32")]),
    0x5B: ("SpecificGhouliesKilledCondition", [("count", "u32"), ("tag", T), ("delay", "f32")]),
    0x5C: ("Op5CByTag", [("tag", T)]),
    0x5D: ("Op5DByTag", [("tag", T)]),
    0x5E: ("SetValuesByTag5E", [("tag", T), ("value1", "f32"), ("value2", "f32")]),
    0x5F: ("CreateRandomCountChallenge", [("minCount", "u32"), ("maxCount", "u32")]),
    0x60: ("Op60ByObjectId", [("objectId", "u32")]),
    0x61: ("SetCameraProperties", [("cameraIndex", "u32"), ("param2", "u32"), ("param3", "u32"), ("param4", "u32")]),
    0x62: ("SetCameraFromMarker", [("markerParam", "u32")]),
    0x63: ("Op63", [("value", "u32")]),
    0x64: ("SetFog", [("enable", "u32"), ("r", "u32"), ("g", "u32"), ("b", "u32"), ("a", "u32"),
                      ("param1", "f32"), ("param2", "f32"), ("param3", "f32"), ("r2", "u32"), ("g2", "u32"), ("b2", "u32")]),
    0x66: ("PlayerDeflectionContactCondition", [("tag", T), ("param", "u32")]),
    0x67: ("SetColliderFlags", [("collider", "hex"), ("enable", "u32")]),
    0x68: ("PlayerHitGhoulyCondition", [("tag", T), ("delay", "f32")]),
    0x69: ("SetScriptBlocking", [("block", "u32"), ("param", "u32")]),
    0x6A: ("GhoulyTriggeredCondition", [("tag", T), ("trigger", "u32"), ("delay", "f32")]),
    0x6B: ("SetTraitorByTag", [("tag", T), ("value", "u32")]),
    0x6C: ("GhoulyExistsInSceneCondition", [("tag", T), ("delay", "f32")]),
    0x6D: ("AddGhoulyByTag", [("tag", T)]),
    0x6F: ("WaitForPlayerDroneAction", []),
    0x70: ("Op70ByTag", [("tag", T), ("value1", "f32"), ("value2", "f32")]),
    0x72: ("ObjectByMarkerBrokenCondition", [("marker", "u32"), ("delay", "f32"), ("param", "u32")]),
    0x73: ("Op73", [("param", "u32")] + [(f"value{i}", "u32") for i in range(1, 10)]),
    0x74: ("Op74", []),
    0x75: ("ActorHasNoEnergyCondition", [("tag", T), ("delay", "f32")]),
    0x76: ("PlayerIgnoreInputsOn", []),
    0x77: ("PlayerIgnoreInputsOff", []),
    0x78: ("Op78ByTag", [("tag", T), ("value", "u32")]),
    0x79: ("Op79", [("value", "u32")]),
    0x7A: ("SetChallengeId", [("challengeId", "s64")]),
    0x7B: ("ChallengeRule7B", []),
    0x7C: ("ChallengeRule7C", []),
    0x7D: ("ChallengeRuleTime", [("seconds", "f32")]),
    0x7E: ("ChallengeRule7E", [("tag", T)]),
    0x7F: ("ChallengeRule7F", [("tag", T)]),
    0x80: ("ChallengeRule80", [("tag", T), ("value", "u32")]),
    0x81: ("ChallengeRule81", []),
    0x82: ("ChallengeRule82", [("tag", T)]),
    0x83: ("ChallengeRule83", [("value", "u32")]),
    0x84: ("ChallengeRule84", []),
    0x85: ("ChallengeRule85", []),
    0x86: ("ChallengeRule86", []),
    0x87: ("CreateChallenge87", []),
    0x88: ("CreateRandomTagTypeChallenge", rep(5, [("tag", T), ("type", "u32"), ("enabled", "u32")]) + [("flag", "u32")]),
    0x89: ("SetFloat89", [("value", "f32")]),
    0x8A: ("DisableMovementSmoothing", [("disable", "u32")]),
    0x8B: ("EveryNthKillCondition", [("n", "u32"), ("tag", T), ("delay", "f32")]),
    0x8C: ("NoGhoulySpawnsActiveCondition", []),
    0x8D: ("PlaySound", [("soundbank", A)]),
    0x8E: ("Op8E", [("param1", "u32"), ("value1", "f32"), ("param2", "u32"), ("value2", "f32"), ("param3", "u32"),
                    ("soundbank", A)]),
    0x8F: ("RotateSomethingByNDegrees", [("degrees", "f32")]),
    0x90: ("SendMessage80ByTag", [("tag", T)]),
    0x91: ("FrightenPlayer", []),
    0x92: ("Challenge21ActiveCondition", []),
    0x93: ("Challenge21NotActiveCondition", []),
    0x94: ("GhoulyEntersRegionCondition", [("tag", T), ("region", "u32")]),
    0x95: ("GhoulyHasEnergyLEQCondition", [("tag", T), ("energy", "u32")]),
    0x96: ("TeleportPlayerToMarker", [("markerIndex", "u32")]),
    0x97: ("SetDroneActionByTag", [("tag", T), ("action", "u32")]),
    0x98: ("SetBackgroundModelFlags", [("entry", "hex"), ("value", "hex")]),
    0x99: ("GhoulySignalCondition", [("tag", T), ("signal", "u32")]),
    0x9A: ("Op9A", []),
    0x9B: ("PlayRumbleAtPlayer", [("fx", A)]),
    0x9C: ("PlayCamShakeAtPlayer", [("fx", A)]),
    0x9D: ("RescuePrisoner", [("prisonerId", "u32")]),
    0x9E: ("Op9E", [("id", "u32"), ("flag1", "u32"), ("flag2", "u32")]),
    0x9F: ("SetModelFlagByTag", [("tag", T), ("index", "u32"), ("value", "u32")]),
    0xA0: ("PlayerMessage2C", []),
    0xA1: ("OpA1", [("value", "u32")]),
    0xA2: ("SetChapterFlagA2", [("value", "u32")]),
    0xA3: ("ObjectByMarkerNotBrokenCondition", [("marker", "u32")]),
    0xA4: ("SetFlagA4", [("value", "u32")]),
    0xA6: ("OpA6", []),
}
BY_NAME = {name: op for op, (name, _f) in SPEC.items()}
CONDITIONS = {0x3D, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x44, 0x47, 0x48, 0x5A, 0x5B, 0x65, 0x66, 0x68, 0x6A,
              0x6C, 0x72, 0x75, 0x8B, 0x8C, 0x92, 0x93, 0x94, 0x95, 0x99, 0xA3}


def type_size(t):
    if t in ("u32", "f32", "hex"):
        return 4
    if t == "u8":
        return 1
    if t == T:
        return 64
    if t == A:
        return 128
    return int(t[1:])


def fmt_float(b):
    f = struct.unpack("<f", b)[0]
    for digits in range(6, 10):
        s = f"{f:.{digits}g}"
        if struct.pack("<f", float(s)) == b:
            return s if any(c in s for c in ".en") else s + ".0"
    return "0x" + b[::-1].hex()  # NaN or odd payload: exact bits


def esc(s):
    out = []
    for ch in s:
        if ch in '"\\':
            out.append("\\" + ch)
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            out.append(f"\\x{ord(ch):02x}")
    return "".join(out)


def fmt_string(b):
    nul = b.find(b"\0")
    text, tail = (b, b"") if nul < 0 else (b[:nul], b[nul + 1:])
    s = '"' + esc(text.decode("latin-1")) + '"'
    if nul < 0:
        s += "!"  # no terminator: fills the whole field
    elif tail.strip(b"\0"):
        s += "~" + tail.rstrip(b"\0").hex()  # leftover bytes after the terminator (editor junk)
    return s


def disasm(data):
    lines, depth, o = [], 0, 0
    while o + 8 <= len(data):
        size, op = struct.unpack_from("<II", data, o)
        operands = data[o + 8:o + size]
        name, fields = SPEC.get(op, (f"Op_0x{op:02X}", None))
        if fields is not None and sum(type_size(t) for _, t in fields) != len(operands):
            fields = None
        if op in (0x0F, 0x3C):
            depth = max(depth - 1, 0)
        parts = [name]
        if fields is None:
            if operands:
                parts.append(f"raw={operands.hex()}")
        else:
            k = 0
            for fname, ft in fields:
                b = operands[k:k + type_size(ft)]
                k += len(b)
                if ft == "u32":
                    v = str(struct.unpack("<I", b)[0])
                elif ft == "hex":
                    v = f"0x{struct.unpack('<I', b)[0]:x}"
                elif ft == "f32":
                    v = fmt_float(b)
                elif ft == "u8":
                    v = str(b[0])
                else:
                    v = fmt_string(b)
                parts.append(f"{fname}={v}")
        lines.append("    " * depth + " ".join(parts))
        if op == 0x0E or op in CONDITIONS:
            depth += 1
        o += size
        if op == 0:
            break
    trailing = data[o:]
    if trailing:
        lines.append(f"; trailing={trailing.hex()}")
    return "\n".join(lines) + "\n"


TOKEN = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"!?(?:~[0-9a-f]+)?|\S+)')


def unesc(s):
    return re.sub(r"\\x([0-9a-f]{2})|\\(.)", lambda m: chr(int(m.group(1), 16)) if m.group(1) else m.group(2), s)


def enc_string(v, size):
    m = re.fullmatch(r'"((?:[^"\\]|\\.)*)"(!?)(?:~([0-9a-f]+))?', v)
    text = unesc(m.group(1)).encode("latin-1")
    if m.group(2):
        b = text
    else:
        b = text + b"\0" + bytes.fromhex(m.group(3) or "")
    if len(b) > size:
        raise ValueError(f"string too long for {size}-byte field: {v}")
    return b.ljust(size, b"\0")


def asm(text):
    out = bytearray()
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(";"):
            if line.startswith("; trailing="):
                out += bytes.fromhex(line.split("=", 1)[1])
            continue
        name, _, rest = line.partition(" ")
        args = dict(TOKEN.findall(rest))
        if name.startswith("Op_0x"):
            op, fields = int(name[5:], 16), None
        else:
            op = BY_NAME[name]
            fields = SPEC[op][1]
        if "raw" in args and (fields is None or not fields or "raw" not in [f for f, _ in fields]):
            body = bytes.fromhex(args["raw"])
        elif fields is None:
            body = b""
        else:
            body = bytearray()
            for fname, ft in fields:
                v = args[fname]
                if ft in ("u32", "hex"):
                    body += struct.pack("<I", int(v, 0))
                elif ft == "u8":
                    body.append(int(v, 0))
                elif ft == "f32":
                    body += bytes.fromhex(v[2:])[::-1] if v.startswith("0x") else struct.pack("<f", float(v))
                else:
                    body += enc_string(v, type_size(ft))
        out += struct.pack("<II", len(body) + 8, op) + body
    return bytes(out)


def scripts_in(root):
    found = {}
    for d in Path(root).rglob("Script__*"):
        found.setdefault(d.name[len("Script__"):], d / "descriptor")
    return found


def main():
    cmd = sys.argv[1]
    if cmd == "disasm":
        text = disasm(Path(sys.argv[2]).read_bytes())
        if len(sys.argv) > 3:
            Path(sys.argv[3]).write_text(text)
        else:
            sys.stdout.write(text)
    elif cmd == "asm":
        Path(sys.argv[3]).write_bytes(asm(Path(sys.argv[2]).read_text()))
    elif cmd == "roundtrip":
        ok = bad = 0
        unknown = set()
        for name, desc in sorted(scripts_in(sys.argv[2]).items()):
            data = desc.read_bytes()
            text = disasm(data)
            unknown |= set(re.findall(r"^\s*(Op_0x\w+)", text, re.M))
            if asm(text) == data:
                ok += 1
            else:
                bad += 1
                print("MISMATCH", name)
        print(f"round-trip: {ok} identical, {bad} different; opcodes without a spec: {sorted(unknown) or 'none'}")
    elif cmd == "dumpall":
        out = Path(sys.argv[3])
        out.mkdir(parents=True, exist_ok=True)
        for name, desc in sorted(scripts_in(sys.argv[2]).items()):
            text = f"; {name}\n; disassembled by ghoul_script.py; reassemble with: ghoul_script.py asm\n" + disasm(desc.read_bytes())
            (out / f"{name}.gscript").write_text(text)
        print(f"wrote {len(scripts_in(sys.argv[2]))} scripts to {out}")


if __name__ == "__main__":
    main()
