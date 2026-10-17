# Grabbed by the Ghoulies: scene scripts

Every room and scene in the game is driven by a `Script` asset: 166 scripts, 5,552 instructions,
150 opcodes. They're in `bundles/aid_script/*.bnl` and the scene bundles. This document comes
from the game's own interpreter in `default.xbe`, read with the annotated ghoulies-decomp Ghidra
project. `ghoul_script.py` disassembles all 166 scripts and reassembles them byte for byte.
Readable versions of every script are in `..\scripts\*.gscript`.

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
| 0x00 | **EndScript** | - | 166 | 166 |
| 0x01 | **SetBackground** | `model`: char[128] asset | 152 | 152 |
| 0x02 | **AddSceneControl** | `objparams`: char[128] asset | 25 | 24 |
| 0x03 | **LoadPackage** | `package`: char[128] asset | 1 | 1 |
| 0x04 | **SetSceneFlags** | `flags`: u32 (hex) | 22 | 22 |
| 0x05 | **Op05** | `value`: u32 | 27 | 27 |
| 0x06 | **SetNumSuperScaryInputs** | `count`: u32 | 11 | 11 |
| 0x07 | **SetSceneValue07** | `value`: u32 | 121 | 121 |
| 0x08 | **SetMindFloatByTag** | `tag`: char[64] tag, `value`: float | 15 | 10 |
| 0x09 | **SetNoAttackTimer** | `tag`: char[64] tag, `seconds`: float | 3 | 3 |
| 0x0A | **SetSceneName** | `loctextKey`: char[64], `showTitle`: u32, `fadeTime`: float, `duration`: float | 128 | 126 |
| 0x0B | **SetPlayerObjParams** | `slot`: u8, `objparams`: char[131] | 4 | 4 |
| 0x0E | **SetPlayState** | `playerControllable`: u32, `playType`: u32, `description`: char[128] asset, `requiredState`: u32, `skipIfBusy`: u32 | 549 | 151 |
| 0x0F | **WaitForMoveOn** | - | 549 | 151 |
| 0x10 | **WaitForMoveOnSimple** | - | 9 | 8 |
| 0x11 | **MoveOn** | - | 140 | 70 |
| 0x12 | **SetActionsEnabled** | `enabled`: u32 | 4 | 2 |
| 0x13 | **PlayCutscene** | `cutscene`: char[128] asset, `waitForEnd`: u32, `restoreActions`: u32 | 141 | 82 |
| 0x14 | **ShowDialog** | `speakerTag`: char[64] tag, `dialog`: char[64], `randomVariants`: u32, `skipIfBusy`: u32, `playOnce`: u32, `onceSlot`: u32 | 100 | 54 |
| 0x15 | **PlayMovieClip** | `movie`: char[128] asset, `param1`: u32, `param2`: u32 | 3 | 3 |
| 0x17 | **PlayEventIntro** | `challengeListId`: u32, `param`: u32, `exitPrevious`: u32, `title`: char[64] | 78 | 68 |
| 0x18 | **EndDescribingChallenge** | - | 78 | 68 |
| 0x19 | **CreateKillAllChallenge** | - | 10 | 10 |
| 0x1A | **CreateTimeLimitChallenge** | `seconds`: float | 16 | 16 |
| 0x1B | **CreateXChallenge** | - | 7 | 7 |
| 0x1C | **CreateKillAllByTagChallenge** | `tag`: char[64] tag, `flag`: u32 | 33 | 28 |
| 0x1D | **CreateKillNByTagChallenge** | `minCount`: u32, `maxCount`: u32, `tag`: char[64] tag | 5 | 5 |
| 0x1E | **CreateTimedChallenge1E** | `seconds`: float | 5 | 5 |
| 0x1F | **CreateFindTheGhoulieKeyChallenge** | - | 5 | 5 |
| 0x21 | **CreateDontKillByTagChallenge** | `tag`: char[64] tag | 6 | 6 |
| 0x22 | **CreateChallenge22** | - | 5 | 5 |
| 0x23 | **CreateWeaponsOnlyChallenge** | - | 8 | 8 |
| 0x25 | **CreateNextOneDifferentChallenge** | `tag1`: char[64] tag, `enabled1`: u32, `tag2`: char[64] tag, `enabled2`: u32, `tag3`: char[64] tag, `enabled3`: u32, `tag4`: char[64] tag, `enabled4`: u32, `tag5`: char[64] tag, `enabled5`: u32 | 6 | 6 |
| 0x26 | **CreateChallenge26** | - | 6 | 5 |
| 0x27 | **CreateFindTheKeyChallenge** | `count`: u32 | 7 | 7 |
| 0x28 | **CreateNoBreakHouseChallenge** | - | 7 | 7 |
| 0x29 | **UpdateDoor** | `doorId`: u32, `state`: u32, `waitUntilDone`: u32, `param`: u32 | 553 | 121 |
| 0x2A | **SpawnGhoulyWithBox** | `ghoulybox`: char[128] asset, `boxId`: u32, `actorAttribs`: char[128] asset, `waitForOpen`: u32 | 170 | 58 |
| 0x2B | **ExecuteGhoulyspawn** | `ghoulyspawn`: char[128] asset | 62 | 34 |
| 0x2C | **PlayerAction2C** | - | 2 | 2 |
| 0x2D | **SpawnPlayer** | - | 2 | 2 |
| 0x2E | **PlayerSetState2E** | `value`: u32 | 0 | 0 |
| 0x2F | **SetPlayerWorried** | - | 57 | 46 |
| 0x30 | **EndPlayerDroneAction** | - | 58 | 46 |
| 0x31 | **SetPlayerWeapon** | `objparams`: char[128] asset | 38 | 36 |
| 0x32 | **SetVar32** | `value`: u32 | 42 | 40 |
| 0x33 | **SetVar33** | `value`: u32 | 4 | 3 |
| 0x34 | **SetVar34ByTag** | `value`: u32, `tag`: char[64] tag | 62 | 35 |
| 0x35 | **SetVar35** | `value`: u32 | 26 | 15 |
| 0x36 | **SetVar36ByTag** | `value`: u32, `tag`: char[64] tag | 108 | 38 |
| 0x37 | **SetVar37** | `value`: float | 0 | 0 |
| 0x38 | **SetVar38** | `value`: u32 | 0 | 0 |
| 0x3A | **PlayCutsceneStream** | `soundbank`: char[128] asset | 6 | 5 |
| 0x3B | **StopSound** | - | 67 | 59 |
| 0x3C | **EndCondition** | - | 384 | 95 |
| 0x3D | **TimeoutCondition** *(condition)* | `seconds`: u32, `flag`: u32 | 57 | 35 |
| 0x3E | **NumberGhouliesAliveCondition** *(condition)* | `count`: u32, `delay`: float | 10 | 10 |
| 0x3F | **ScareSourceProximityCondition** *(condition)* | - | 1 | 1 |
| 0x40 | **ObjectPickedUpCondition** *(condition)* | `tag`: char[64] tag, `delay`: float | 5 | 4 |
| 0x41 | **NumberGhouliesKilledCondition** *(condition)* | `count`: u32, `delay`: float | 15 | 7 |
| 0x42 | **NumberOfKnockdownsCondition** *(condition)* | `count`: u32, `tag`: char[64] tag, `delay`: float | 4 | 4 |
| 0x43 | **PlayerApproachesDoorCondition** *(condition)* | `doorId`: u32, `minDistance`: float | 11 | 11 |
| 0x44 | **HauntedObjectActivatedCondition** *(condition)* | `tag`: char[64] tag | 7 | 7 |
| 0x45 | **StartChallengeMusic** | - | 106 | 103 |
| 0x46 | **ResetPlayerWeapon** | - | 14 | 13 |
| 0x47 | **PlayerEntersRegionCondition** *(condition)* | `region`: u32 | 116 | 53 |
| 0x48 | **PlayerLeavesRegionCondition** *(condition)* | `region`: u32 | 1 | 1 |
| 0x49 | **SetGlobalFlags** | `mask`: u32 (hex) | 9 | 8 |
| 0x4A | **ClearGlobalFlags** | `mask`: u32 (hex) | 4 | 4 |
| 0x4B | **SetLighting** | `colour1`: u32 (hex), `intensity`: float, `enable`: u32, `start1`: float, `end1`: float, `param`: float, `start2`: float, `end2`: float, `colour2`: u32 (hex) | 4 | 4 |
| 0x4C | **Op4C** | `value`: u32 | 140 | 139 |
| 0x4E | **RandomEvent** | `param`: u32, `event`: u32, `chancePercent`: float | 1 | 1 |
| 0x4F | **SetDoorInitialState** | `doorId`: u32, `state`: u32 | 10 | 8 |
| 0x50 | **CreateRandomTagChallenge** | `tag1`: char[64] tag, `enabled1`: u32, `tag2`: char[64] tag, `enabled2`: u32, `tag3`: char[64] tag, `enabled3`: u32, `tag4`: char[64] tag, `enabled4`: u32, `tag5`: char[64] tag, `enabled5`: u32, `flag`: u32 | 2 | 2 |
| 0x51 | **ActivateObjectsByTag** | `tag`: char[64] tag, `instanceId`: u32 | 81 | 37 |
| 0x52 | **Op52** | `name`: char[128] asset | 0 | 0 |
| 0x53 | **PlayWalkinCutscene** | `cutscene`: char[128] asset | 42 | 42 |
| 0x55 | **PlayMusicByActorTag** | `tag`: char[64] tag | 96 | 80 |
| 0x56 | **Op56** | `value`: u32 | 7 | 7 |
| 0x57 | **PlayRoomAmbience** | `soundbank`: char[128] asset | 2 | 2 |
| 0x58 | **SetActorStrategyByTag** | `tag`: char[64] tag, `strategy`: char[64] | 6 | 6 |
| 0x59 | **SendMessageToTag** | `tag`: char[64] tag | 1 | 1 |
| 0x5A | **SpecificGhouliesAliveCondition** *(condition)* | `count`: u32, `tag`: char[64] tag, `delay`: float | 12 | 10 |
| 0x5B | **SpecificGhouliesKilledCondition** *(condition)* | `count`: u32, `tag`: char[64] tag, `delay`: float | 42 | 16 |
| 0x5C | **Op5CByTag** | `tag`: char[64] tag | 26 | 21 |
| 0x5D | **Op5DByTag** | `tag`: char[64] tag | 1 | 1 |
| 0x5E | **SetValuesByTag5E** | `tag`: char[64] tag, `value1`: float, `value2`: float | 1 | 1 |
| 0x5F | **CreateRandomCountChallenge** | `minCount`: u32, `maxCount`: u32 | 8 | 8 |
| 0x60 | **Op60ByObjectId** | `objectId`: u32 | 69 | 27 |
| 0x61 | **SetCameraProperties** | `cameraIndex`: u32, `param2`: u32, `param3`: u32, `param4`: u32 | 151 | 120 |
| 0x62 | **SetCameraFromMarker** | `markerParam`: u32 | 26 | 17 |
| 0x63 | **Op63** | `value`: u32 | 1 | 1 |
| 0x64 | **SetFog** | `enable`: u32, `r`: u32, `g`: u32, `b`: u32, `a`: u32, `param1`: float, `param2`: float, `param3`: float, `r2`: u32, `g2`: u32, `b2`: u32 | 4 | 4 |
| 0x66 | **PlayerDeflectionContactCondition** *(condition)* | `tag`: char[64] tag, `param`: u32 | 7 | 5 |
| 0x67 | **SetColliderFlags** | `collider`: u32 (hex), `enable`: u32 | 47 | 13 |
| 0x68 | **PlayerHitGhoulyCondition** *(condition)* | `tag`: char[64] tag, `delay`: float | 20 | 11 |
| 0x69 | **SetScriptBlocking** | `block`: u32, `param`: u32 | 14 | 7 |
| 0x6A | **GhoulyTriggeredCondition** *(condition)* | `tag`: char[64] tag, `trigger`: u32, `delay`: float | 12 | 6 |
| 0x6B | **SetTraitorByTag** | `tag`: char[64] tag, `value`: u32 | 6 | 3 |
| 0x6C | **GhoulyExistsInSceneCondition** *(condition)* | `tag`: char[64] tag, `delay`: float | 17 | 14 |
| 0x6D | **AddGhoulyByTag** | `tag`: char[64] tag | 0 | 0 |
| 0x6F | **WaitForPlayerDroneAction** | - | 1 | 1 |
| 0x70 | **Op70ByTag** | `tag`: char[64] tag, `value1`: float, `value2`: float | 4 | 2 |
| 0x72 | **ObjectByMarkerBrokenCondition** *(condition)* | `marker`: u32, `delay`: float, `param`: u32 | 19 | 3 |
| 0x73 | **Op73** | `param`: u32, `value1`: u32, `value2`: u32, `value3`: u32, `value4`: u32, `value5`: u32, `value6`: u32, `value7`: u32, `value8`: u32, `value9`: u32 | 7 | 7 |
| 0x74 | **Op74** | - | 1 | 1 |
| 0x75 | **ActorHasNoEnergyCondition** *(condition)* | `tag`: char[64] tag, `delay`: float | 1 | 1 |
| 0x76 | **PlayerIgnoreInputsOn** | - | 3 | 3 |
| 0x77 | **PlayerIgnoreInputsOff** | - | 2 | 2 |
| 0x78 | **Op78ByTag** | `tag`: char[64] tag, `value`: u32 | 20 | 10 |
| 0x79 | **Op79** | `value`: u32 | 2 | 2 |
| 0x7A | **SetChallengeId** | `challengeId`: char[64] | 20 | 20 |
| 0x7B | **ChallengeRule7B** | - | 20 | 20 |
| 0x7C | **ChallengeRule7C** | - | 6 | 6 |
| 0x7D | **ChallengeRuleTime** | `seconds`: float | 11 | 11 |
| 0x7E | **ChallengeRule7E** | `tag`: char[64] tag | 3 | 3 |
| 0x7F | **ChallengeRule7F** | `tag`: char[64] tag | 3 | 2 |
| 0x80 | **ChallengeRule80** | `tag`: char[64] tag, `value`: u32 | 3 | 3 |
| 0x81 | **ChallengeRule81** | - | 1 | 1 |
| 0x82 | **ChallengeRule82** | `tag`: char[64] tag | 1 | 1 |
| 0x83 | **ChallengeRule83** | `value`: u32 | 2 | 2 |
| 0x84 | **ChallengeRule84** | - | 1 | 1 |
| 0x85 | **ChallengeRule85** | - | 1 | 1 |
| 0x86 | **ChallengeRule86** | - | 1 | 1 |
| 0x87 | **CreateChallenge87** | - | 1 | 1 |
| 0x88 | **CreateRandomTagTypeChallenge** | `tag1`: char[64] tag, `type1`: u32, `enabled1`: u32, `tag2`: char[64] tag, `type2`: u32, `enabled2`: u32, `tag3`: char[64] tag, `type3`: u32, `enabled3`: u32, `tag4`: char[64] tag, `type4`: u32, `enabled4`: u32, `tag5`: char[64] tag, `type5`: u32, `enabled5`: u32, `flag`: u32 | 1 | 1 |
| 0x89 | **SetFloat89** | `value`: float | 2 | 1 |
| 0x8A | **DisableMovementSmoothing** | `disable`: u32 | 1 | 1 |
| 0x8B | **EveryNthKillCondition** *(condition)* | `n`: u32, `tag`: char[64] tag, `delay`: float | 12 | 8 |
| 0x8C | **NoGhoulySpawnsActiveCondition** *(condition)* | - | 4 | 3 |
| 0x8D | **PlaySound** | `soundbank`: char[128] asset | 11 | 9 |
| 0x8E | **Op8E** | `param1`: u32, `value1`: float, `param2`: u32, `value2`: float, `param3`: u32, `soundbank`: char[128] asset | 1 | 1 |
| 0x8F | **RotateSomethingByNDegrees** | `degrees`: float | 5 | 5 |
| 0x90 | **SendMessage80ByTag** | `tag`: char[64] tag | 4 | 4 |
| 0x91 | **FrightenPlayer** | - | 4 | 2 |
| 0x92 | **Challenge21ActiveCondition** *(condition)* | - | 1 | 1 |
| 0x93 | **Challenge21NotActiveCondition** *(condition)* | - | 2 | 2 |
| 0x94 | **GhoulyEntersRegionCondition** *(condition)* | `tag`: char[64] tag, `region`: u32 | 2 | 2 |
| 0x95 | **GhoulyHasEnergyLEQCondition** *(condition)* | `tag`: char[64] tag, `energy`: u32 | 1 | 1 |
| 0x96 | **TeleportPlayerToMarker** | `markerIndex`: u32 | 7 | 5 |
| 0x97 | **SetDroneActionByTag** | `tag`: char[64] tag, `action`: u32 | 1 | 1 |
| 0x98 | **SetBackgroundModelFlags** | `entry`: u32 (hex), `value`: u32 (hex) | 4 | 2 |
| 0x99 | **GhoulySignalCondition** *(condition)* | `tag`: char[64] tag, `signal`: u32 | 4 | 1 |
| 0x9A | **Op9A** | - | 1 | 1 |
| 0x9B | **PlayRumbleAtPlayer** | `fx`: char[128] asset | 1 | 1 |
| 0x9C | **PlayCamShakeAtPlayer** | `fx`: char[128] asset | 1 | 1 |
| 0x9D | **RescuePrisoner** | `prisonerId`: u32 | 11 | 10 |
| 0x9E | **Op9E** | `id`: u32, `flag1`: u32, `flag2`: u32 | 15 | 12 |
| 0x9F | **SetModelFlagByTag** | `tag`: char[64] tag, `index`: u32, `value`: u32 | 2 | 2 |
| 0xA0 | **PlayerMessage2C** | - | 4 | 4 |
| 0xA1 | **OpA1** | `value`: u32 | 3 | 3 |
| 0xA2 | **SetChapterFlagA2** | `value`: u32 | 1 | 1 |
| 0xA3 | **ObjectByMarkerNotBrokenCondition** *(condition)* | `marker`: u32 | 1 | 1 |
| 0xA4 | **SetFlagA4** | `value`: u32 | 1 | 1 |
| 0xA6 | **OpA6** | - | 1 | 1 |
