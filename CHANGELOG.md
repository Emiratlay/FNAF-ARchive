# Changelog

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
