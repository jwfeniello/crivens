"""Generate SCRIPTS.md (script VM + opcode reference) from ghoul_script.SPEC and usage counts.
usage: python -I script_docs.py <assets_dir> <out.md>
"""
import collections
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghoul_script as gs  # noqa: E402

uses = collections.Counter()
in_scripts = collections.defaultdict(set)
for name, desc in gs.scripts_in(sys.argv[1]).items():
    data = desc.read_bytes()
    o = 0
    while o + 8 <= len(data):
        size, op = struct.unpack_from("<II", data, o)
        uses[op] += 1
        in_scripts[op].add(name)
        o += size
        if op == 0:
            break

TYPE_DOC = {"u32": "u32", "f32": "float", "hex": "u32 (hex)", "u8": "u8", "tag": "char[64] tag", "aid": "char[128] asset"}


def tdoc(t):
    return TYPE_DOC.get(t, f"char[{t[1:]}]")


head = """# Grabbed by the Ghoulies: scene scripts

Every room and scene in the game is driven by a `Script` asset: 166 scripts, 5,552 instructions,
150 opcodes. They're in `bundles/aid_script/*.bnl` and the scene bundles. This document comes
from the game's own interpreter in `default.xbe`, read with the annotated ghoulies-decomp Ghidra
project. `ghoul_script.py` disassembles all 166 scripts and reassembles them byte for byte.
Readable versions of every script are in `..\\scripts\\*.gscript`.

## Bytecode

An instruction is `u32 size` (including this 8-byte header), `u32 opcode`, then operands.
Each opcode always has the same operand size. Strings are fixed-size, NUL-padded fields:
**tag** = `char[64]` (`objTag_Actor_Pirate`, `challengeId_Time`, ...) and **asset** = `char[128]`
(`aid_cutscene_...`, `XACT_SOUNDBANK_...`). The game's tools sometimes left stale bytes after the
NUL. The disassembler keeps them as a `~hex` suffix so reassembly is exact.

## The VM (`Scripting::ExecuteScript`, 0x128a00)

`EventLoop::RunScripts` runs every loaded script each frame. For the current instruction,
`ExecuteScript` tries the 17 functions in the `ScriptHandlers` table (0x312650) in order. The
first one that recognises the opcode returns one of:

| Return | Meaning |
|---|---|
| `Completed` (2) | advance to the next instruction and keep running this frame |
| `Halted` (0) | stop for this frame and retry the same instruction next frame (waits, cutscenes, dialogue) |
| `Skipped` (1) | end of this block (`EndScript`, `EndCondition`) |
| `SkipHandler` (3) | not mine, so try the next handler. An opcode no handler claims is skipped. |

Handlers also get two flags: "game is loading" and "setup pass". Setup-type opcodes (doors,
weapons, objparams) record state during loading instead of acting.

## Structure

```
SetPlayState playerControllable=.. playType=.. description="..."   ; begin a "play" (stage)
    ...instructions...
    PlayerEntersRegionCondition region=3      ; register a trigger
        ...body: runs later, when the trigger fires...
    EndCondition
WaitForMoveOn                                 ; wait here until a MoveOn
```

* **Plays.** `SetPlayState` starts a stage. If its requirement fails (`requiredState`, `skipIfBusy`),
  it jumps ahead to the stage's `WaitForMoveOn` (`ScriptInstance::seekToOp`). `WaitForMoveOn`
  halts until something runs `MoveOn`, usually a condition body or a finished challenge.
* **Conditions.** A condition instruction registers `(conditionId, pointer to the next instruction)`
  with `Scripting::newScriptCondition`, then the VM skips to `EndCondition`. When the condition
  fires (timer, region entered, ghoulies killed, object broken, ...), its body runs as its own
  script until `EndCondition`. Most conditions take an extra `delay` float.
* **Challenges.** `PlayEventIntro` opens a challenge list. `SetChallengeId` / `ChallengeRule*` /
  `Create*Challenge` set up the rules (time limits, "don't kill X", "weapons only"...), and
  `EndDescribingChallenge` shows the challenge card.

## Opcode reference

Field order is the byte order. Names ending in a hex number (`Op4C`, `SetVar32`,
`ChallengeRule7E`...) are opcodes whose handler is known but whose purpose is still vague; the
handler code is the place to refine them.

| Op | Name | Operands | Uses | Scripts |
|---|---|---|---|---|
"""
rows = []
for op in sorted(gs.SPEC):
    name, fields = gs.SPEC[op]
    ops = ", ".join(f"`{f}`: {tdoc(t)}" for f, t in fields) or "-"
    kind = " *(condition)*" if op in gs.CONDITIONS else ""
    rows.append(f"| 0x{op:02X} | **{name}**{kind} | {ops} | {uses[op]} | {len(in_scripts[op])} |")
Path(sys.argv[2]).write_text(head + "\n".join(rows) + "\n")
print(f"wrote {sys.argv[2]}: {len(rows)} opcodes ({sum(1 for op in gs.SPEC if uses[op])} used by the game)")
