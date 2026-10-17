# Changelog

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
