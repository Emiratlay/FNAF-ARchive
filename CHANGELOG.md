# Changelog

## v1.3

### Server
- **Express delivery fixed.** The game reads `UpdateAnimatronicEntities` as a *list*. It also applies an update only when the animatronic's state changes. The update is now a list, and the animatronic switches to "approaching" so it actually comes to you.
- **Radio Jammer and Friend-or-Foe Transponder fixed.** `DeviceEntry.IsExpired` compares expiry times in **milliseconds**, but they were sent in seconds. Timed devices now last exactly as the game data says: Jammer 2 hours, Transponder 3 days. Old saves are converted automatically.
- **Scavenging gives real loot.** Every trip gives parts. You also get one common reward: a mod chip, Faz-Coins or a device/lure from the game's loot table. Mod stars grow with trip length (30 min 1★, 1–2 h up to 2★, 4 h up to 3★). There is also a rare reward (a character CPU or a 3★ mod) and a plush suit chance. Salvage mod chips equipped on the endo now change the parts, reward and plush suit chances.
- **Encounter drops:**
  - Plush suit, CPU and mod drops are now rolled independently, so several can drop at once.
  - The drop chances from the game data are multiplied by 1.5 (`DROP_CHANCE_MULTIPLIER`).
  - Note: 12–13 parts is the game's real reward for Basic Freddy and Chica. Higher-streak animatronics pay much more.
- **Streak progression (`PROGRESSION_DATA`):**
  - A new best streak pays bonus parts: 13, 25, 45, 73…
  - Streaks 5, 9 and 13 unlock extra endoskeleton slots.

### Editor
- **Active devices → Switch off** stops any running device (Radio Jammer, Transponder, EMF Meter…) on the next save.


## v1.2

### Server
- **Send to yourself.** The game's Send screen needs a friend as the target, and offline the friends list was empty, so sending never showed up. The friends list now contains **"Me (offline)"**. Anything sent to it comes back to attack you.
- **Shadow Bonnie Lure:**
  - The game only starts Shadow Bonnie from its own remnant-threat check (`ThreatEvaluator.CheckForThreatSpawn`), which rarely fires. The new built-in lure device calls it on demand.
  - It is in the store (500 Faz-Coins for 3) and brings Shadow Bonnie in about 10 seconds.
  - Difficulty rises with each win: Easy → Medium → Hard → Insane.
- Built-in additions (the Shadow Bonnie Lure device, store item and texts) are served as master data. The served version moved to 2000+, so phones re-download it once.
- `test_kayitlar.py` replays the recordings: 798 requests, 0 differences.

### Editor
- **Devices** section under Money: add or remove any lure (including the Shadow Bonnie Lure) or device.
- Fixed device counts not being saved after a previous save in the same session.

### Tools
- Ghidra 12.1.4 can be connected to REA for decompiling `libil2cpp.so`. This is optional; see `tools/il2dis.py` for the lightweight path.

## v1.1

### Editor app
- New **CPUs** tab:
  - Add or remove any player CPU (Freddy, Toy Bonnie, Springtrap…) in your inventory.
  - **Create your own CPU.** Pick a base CPU for the behaviour and a character for the look, then tune charge chance, jumpscare chance, shock window, circling speed, initial pause, disruption chance, map speed, aggression and parts reward. The CPU gets its own attack profile and can optionally spawn in the wild.
- Deleting a custom CPU also removes it from your inventory, from endoskeletons and from animatronics on the map.

### Server
- **Express delivery** now works for animatronics on the map. It charges 50 Faz-Coins, and the game receives the update through `UpdateAnimatronicEntities`.
- **Salvage Scanner** gives +25% parts on the next win and uses its charge.
- **EMF Meter** makes rare remnant colours likelier and uses one charge per remnant node.
- Timed devices expire on schedule. Activation no longer fails if the device count drifted.
- Custom CPUs drop themselves when defeated.
- `custom.json` supports an `attacks` section (appended to `ATTACK_DATA`).
- `test_offline.py` covers express delivery, both devices and custom CPUs.

### Tools
- `tools/il2dis.py` now resolves IL2CPP string literals through the ELF relocation table. This is how the express delivery response key was found.

## v1.0.1

- 40 CloudScript calls emulated: workshop, scavenging, store, devices, sending animatronics, remnant, Shadow Bonnie, daily challenges, profile, item drops.
- `server/test_offline.py` end-to-end test.

## v1.0

- First release: APK patcher, local PlayFab server (PC and Termux modes), editor app (money, mod chips, skins).
