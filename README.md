# FNAF AR Offline

Play **FNaF ARchive 8.0.0**, the preserved build of *Five Nights at Freddy's AR: Special Delivery*, **fully offline** on an Android phone. No game server and no internet connection are needed.

The project has three parts:

- **A patcher** that redirects the game to a local server.
- **A local server** that emulates the game's PlayFab/CloudScript backend.
- **An editor app** for your money, mod chips and skins, including mod chips and skins you design yourself.

You can run the server in two ways:

| | **PC mode** | **Phone-only mode** |
|---|---|---|
| Server runs on | your Windows PC | the phone itself (Termux) |
| Phone connection | USB cable (`adb reverse`) | none |
| Internet | not needed | not needed (only once, to install Termux and Python) |
| Good for | first setup, debugging | playing anywhere |

> **Disclaimer.** This is an unofficial fan project for personal use and preservation. It is not affiliated with Illumix, Scott Cawthon or Forsaken-Gaming. **This repository contains no game files.** You bring your own copy of the ARchive APK, and the scripts patch it on your machine. Do not redistribute patched APKs or game assets.

---

## Contents

1. [How it works](#how-it-works)
2. [What works](#what-works)
3. [Requirements](#requirements)
4. [One-time setup on the PC](#one-time-setup-on-the-pc)
5. [Mode A: Play with the phone connected to the PC](#mode-a-play-with-the-phone-connected-to-the-pc)
6. [Mode B: Play on the phone only (Termux)](#mode-b-play-on-the-phone-only-termux)
7. [Editor app: money, mod chips and skins](#editor-app-money-mod-chips-and-skins)
8. [Troubleshooting](#troubleshooting)
9. [For developers](#for-developers)
10. [Credits](#credits)

---

## How it works

```
                      patched APK
 FNAF AR on phone ──► http://127.0.0.1:9000 ──► server/server.py ──► server/game.py
                                                      │                (game logic, save)
                                                      └──► server/cdn/  (game assets, 1.1 GB)
```

- The game uses Microsoft PlayFab as its backend. The patcher replaces the `playfabapi.com` string inside `global-metadata.dat` with `http://127.0.0.1:9000`, so every request goes to the local server.
- The server answers the game's ~25 CloudScript calls itself. Spawns, rewards, scavenging and the inbox follow the game's **own rules**, read from its master data (spawn tables by win streak, reward ranges and so on).
- Two small patches stop the "Connection Lost" popup that appears when the phone has no internet:
  - the connectivity ping target is changed;
  - one 4-byte code patch is applied in `libil2cpp.so`.
- **PC mode:** `adb reverse` maps the phone's `127.0.0.1:9000` to the PC over USB.
- **Phone-only mode:** the same Python server runs inside Termux on the phone.

## What works

Everything below runs offline. 40 of the game's CloudScript calls are emulated:

- **Login, tutorial, inbox:** inbox messages, remnant milestone messages.
- **Encounters:**
  - wild spawns by win streak (Basic → Haywire → Insane…);
  - winning pays parts and the CPU, plush suit and mod **drops** decided at spawn;
  - losing costs remnant.
- **Workshop:**
  - equip CPUs, plush suits, mod chips and remnant;
  - repair wear and tear;
  - sell mod chips.
- **Scavenging:** send out, collect rewards when it returns, recall.
- **Sending animatronics:** send your endo to yourself; it arrives and attacks with your CPU. Recall and express delivery also work.
- **Store:**
  - devices, lures, character packs, endoskeleton slots, Faz-Coins for parts;
  - prices come from the store list and contents from the game's store data.
- **Devices:** activating salvage scanners, EMF meters and radio jammers. Lures bring the lured animatronic.
- **Remnant:** server-side remnant nodes; the colour decides the amount.
- **Shadow Bonnie:** remnant encounters (Easy → Insane).
- **Daily challenges:** every challenge type, changing a challenge, collecting the reward.
- **Profile:** avatar, display name, friend codes.
- **Editor:** money, inventory, custom mod chips and skins.

How each call was made:

- Calls seen in recordings of the live server are matched field-for-field. Two recording sessions, 798 requests.
- Calls never recorded (sending, recalling attacks, express delivery, Shadow Bonnie, daily reward collection, device expiry) were rebuilt from the client's own response handlers, so they use only keys the game already understands.

**Not available offline:**

- Friends and other players. The leaderboard shows only you, and sending to a friend comes back to you.
- Seasonal events and subscriptions.

Any unknown call still gets a valid empty answer, so the game keeps running. It shows up in `server.log` as `NOT IMPLEMENTED`.

## Requirements

- **A Windows PC** with:
  - [Python 3.8+](https://www.python.org/downloads/) (tick *Add python.exe to PATH* when installing);
  - about 3 GB of free disk space.
- **An Android phone**:
  - arm64, Android 7.0 or newer (tested on a Samsung Galaxy S7, Android 8.0);
  - about 2 GB of free storage for phone-only mode.
- **A USB data cable** (charge-only cables do not work).
- **Your own copy of `FNaF.ARchive.8.0.0.apk`** from the [FNaF-ARchive releases](https://github.com/Forsaken-Gaming/FNaF-ARchive/releases).

> iPhone is not supported. The patcher only works on the Android APK.

---

## One-time setup on the PC

### 1. Get this repository

Use **Code → Download ZIP** on GitHub and extract it, or run:

```bash
git clone https://github.com/Emiratlay/FNAF-ARchive.git
```

### 2. Download the tools

This step downloads a Java runtime, `uber-apk-signer` and `adb` into `tools/`:

```bash
python tools/setup_tools.py
```

### 3. Add your APK

Create the folder `patcher/input/` and put `FNaF.ARchive.8.0.0.apk` in it.

### 4. Build the patched APK

```bash
python patcher/build_apk.py
```

You should see these lines:

```
literal #14422: playfabapi.com -> http://127.0.0.1:9000
literal #19239: 8.8.8.8 -> 127.0.0.1
code patch: Connection Lost dialog disabled
```

The output is `patcher/build/FNaF.AR.8.0.0.offline-aligned-debugSigned.apk`.

### 5. Download the game assets (about 1.1 GB)

```bash
python server/download_cdn.py
```

The files come from the public [Forsaken-AR-CDN](https://github.com/Forsaken-Gaming/Forsaken-AR-CDN) repository into `server/cdn/`. If the download stops, run the command again; finished files are skipped.

### 6. Prepare the phone

1. Enable USB debugging:
   1. Go to **Settings → About phone → Software information** and tap **Build number** 7 times.
   2. Go to **Settings → Developer options** and turn on **USB debugging**.
2. **Uninstall any other FNAF AR / ARchive build.** The signatures differ, so the patched APK cannot be installed over it.
3. Connect the phone with USB. When the phone asks *Allow USB debugging?*, tick **Always allow** and tap **Allow**.

> If `adb devices` (or the window from the next step) shows no device on Windows, install the [Samsung USB driver](https://developer.samsung.com/android-usb-driver) (or your phone maker's driver) and reconnect.

### 7. Install the game

Run **`windows/1_install_game.bat`**. It should list your phone and end with `Success`.

---

## Mode A: Play with the phone connected to the PC

Do this **every time** you play:

1. Connect the phone with USB.
2. Run **`windows/3_offline_mode.bat`** and keep the window open. It should show:
   ```
   Server started: mode=offline port=9000
   ```
   If Windows Firewall asks about Python, allow it.
3. Open the game on the phone. Requests stream into the window, for example `offline /Client/LoginWithCustomID -> 200` and `CDN /cdn/8.0.0/...`.
4. You can turn off Wi-Fi and mobile data on the phone and on the PC. The game keeps working.

On the **first launch** the game downloads its assets from the PC, which takes a few minutes. Then the tutorial starts with a new player.

- Your progress is saved on the PC in `server/save/state.json`. Delete that file to start over.
- To stop playing, close the game, then close the server window.

---

## Mode B: Play on the phone only (Termux)

The same server runs inside Termux on the phone, so you need **no cable, no PC and no internet**.

### One-time setup

1. **Install Termux from [F-Droid](https://f-droid.org/packages/com.termux/).** The Play Store version is outdated and does not work.
2. **Install Python inside Termux.** This step needs internet. Open Termux and type each line, pressing Enter after each one:
   ```bash
   pkg update -y
   pkg install -y python
   termux-setup-storage
   ```
   `termux-setup-storage` asks for file access. Tap **Allow**.
3. **Copy the server to the phone.** Connect the phone to the PC with USB and run **`windows/6_push_server_to_phone.bat`**. This copies about 1.1 GB to the phone's internal storage as `FNAFAR_server`.
   - If you already played in PC mode, your PC save is copied as well, so you continue where you left off.
   - An existing save on the phone is never overwritten.
4. **Add a shortcut command.** In Termux, type:
   ```bash
   echo 'alias fnaf="bash ~/storage/shared/FNAFAR_server/start.sh"' >> ~/.bashrc
   ```
   Then close Termux completely (**Exit** in its notification) and open it again.
5. **Turn off battery optimization for Termux**, otherwise Android may kill the server in the background:
   - Go to **Settings → Apps → Termux → Battery** and turn off optimization.
   - On Samsung phones, also check that Termux is **not** in **Settings → Device care → Battery → Sleeping apps**.

Check the copy with this command:

```bash
ls ~/storage/shared/FNAFAR_server
```

The list should contain `cdn`, `game.py`, `save`, `server.py`, `start.sh` and `templates`.

### Every time you play

1. Open Termux and type `fnaf`. Wait for `Server started: mode=offline port=9000`.
2. Press the **Home** button (not Back) and open the game.
3. When you are done, go back to Termux and press **CTRL** (on the extra-keys row) and then **c**.

> **Always start the server first.** The "Connection Lost" popup is disabled, so without the server the game silently hangs while loading instead of showing an error.

- Your save now lives on the phone (`FNAFAR_server/save/state.json`). From here on it is separate from the PC save.
- The server log is `FNAFAR_server/server.log`.

---

## Editor app: money, mod chips and skins

**FNAF AR Editor** is a small Android app (about 25 KB) that edits the phone-only server's files in `/sdcard/FNAFAR_server`. It works without the server running.

### Build and install

1. Download the extra build tools: a JDK, Android build-tools and the Android platform.
   ```bash
   python tools/setup_tools.py --editor
   ```
2. Build the app:
   ```bash
   python editor/build.py
   ```
3. Connect the phone with USB and run **`windows/7_install_editor.bat`**. This installs the app and updates the server code on the phone.
4. If the server is running in Termux, stop it with **CTRL + c** and start it again with `fnaf`.
5. Open **FNAF AR Editor** on the phone and grant the storage permission.

### Using it

1. **Close the game first** (swipe it away from recent apps).
2. Make your changes in the editor and tap **Save changes** at the bottom.
3. Start the server (`fnaf`) and open the game. The new values load on startup.

If you created new mod chips or skins, the game downloads updated game data at startup, so loading takes a bit longer.

| Tab | What it does |
|---|---|
| **Money** | Set Parts, Faz-Coins and Remnant. Quick +100 / +1000 / +10000 buttons. |
| **Mod Chips** | Every mod chip in the game; **+ / −** changes how many you own. **+ Create a new mod chip** lets you design one (see below). |
| **Skins** | Switch on the skins you want to own. **+ Create a new skin** lets you create one (see below). |
| **Custom** | Lists what you created. **Delete** removes an item from the game, your inventory and any endoskeleton it is equipped on. |

**Creating a mod chip.** You choose these fields:

- name and description;
- category (Attack, Disruption, Haywire, Stalking, Map, Static, Salvage, Wear and tear…);
- up to two effects, each with a multiplier;
- star rating and sell value.

For the multiplier, 1.00 means no change, 1.50 means 50% more and 0.50 means half. Each effect shows the range the original game uses. Start close to that range; extreme values can make the game behave strangely.

**Creating a skin.** Choose a name, a description and an existing model to use for the look. The new skin is a separate item with its own name and inventory slot, but it **looks like the model you picked**. Changing the look (textures) is not possible in the app.

**Backups.** Every save keeps the previous file as `.bak` (`save/state.json.bak`, `custom/custom.json.bak`).

**If something goes wrong:**

- To remove all custom content, delete `FNAFAR_server/custom/custom.json`.
- To undo the last change, rename the matching `.bak` file back.

> The editor edits the **phone's** server folder. In PC mode the save is `server/save/state.json` on the PC.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `1_install_game.bat` shows no device, or `unauthorized` | Accept the USB debugging prompt on the phone, use a data cable, install the USB driver. |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | Uninstall the other FNAF AR / ARchive build first. |
| Stuck on a black screen after login | Check `server.log` for `ERROR` lines and open an issue with the log. |
| Loading stops at a percentage, for example 42% | The phone cached an online asset URL from an earlier online session. Run `windows/5_reset_game_data_on_phone.bat` once; your offline save is not affected. |
| `Port 9000 is busy` | Another server window is still open. Close it. |
| Game hangs on loading in phone-only mode | The server is not running, or Android killed Termux. Start `fnaf` again and check the battery settings. |
| `fnaf: command not found` | Redo step 4 of the Termux setup and restart Termux. |
| `No such file or directory` in Termux | Run `termux-setup-storage`, or the server was not copied (`6_push_server_to_phone.bat`). |
| `python: command not found` in Termux | `pkg install -y python` |

To capture the game's log for a bug report, run `windows/4_capture_logcat.bat` while you reproduce the problem. It writes `server/logcat.txt`.

---

## For developers

### Repository layout

```
patcher/   patch_metadata.py (string literal patches), build_apk.py (APK patch + sign)
server/    server.py (HTTP, record/offline), game.py (game logic), templates/ (response shapes),
           download_cdn.py, start.sh (Termux)
editor/    Android app: Java WebView bridge + assets/index.html UI, build.py, test/ (headless UI test)
windows/   numbered helper scripts
tools/     setup_tools.py (downloads JDK/SDK/adb/signer here)
```

### Record mode

`windows/2_record_mode.bat` (or `python server/server.py record`) forwards requests to the live ARchive PlayFab title and saves every request and response in `server/captures/`. This is how the existing logic was reverse engineered. Use it to study calls that are not implemented yet.

> **Captures contain your session tickets and player ids. Never commit or share them.** They are git-ignored.

### Adding a CloudScript function

1. Record the call in record mode.
2. Write a `cs_<name>(state, params)` function in `server/game.py` that returns the `scriptData` dict.
3. Register the function in `CLOUDSCRIPT`.

Missing top-level result fields can crash the client; for example, `DeviceAuthenticationResponse` needs `newPlayer`. If a call needs such fields, add a `templates/<FunctionName>.json` with a `resultExtras` object.

### Testing the server

`python server/test_offline.py` plays a full session against `game.py` with a throw-away save and checks every feature: drops, remnant, store, devices, lures, workshop, scavenging, sending, Shadow Bonnie, daily challenges and profile.

### Custom content

The editor writes `server/custom/custom.json`. Its `mods`, `plushsuits` and `loc` entries are appended to `MODS_DATA`, `PLUSHSUIT_DATA` and `LOC_DATA`. The served master data version is `800 + custom.version`, so the game re-downloads its data whenever the content changes.

The client parses master data with protobuf's JSON parser, so **custom entries may only use field names that exist in the original entries**.

### Patches

All patch offsets are for the **FNaF ARchive 8.0.0** APK (Unity 2018.4.35f1, IL2CPP metadata v24). `build_apk.py` checks the original bytes and refuses to patch any other build.

### Testing the editor without a phone

The test drives the real UI in headless Edge through a fake `Android` bridge:

1. Copy `server/cdn/8.0.0/Masterdata/800` to `editor/test/data/cdn/8.0.0/Masterdata/800`.
2. Copy a `state.json` to `editor/test/data/save/`.
3. Run the test:
   ```bash
   python editor/test/harness.py
   ```

---

## Credits

- **Illumix** and **Scott Cawthon**: the original game.
- **[Forsaken-Gaming](https://github.com/Forsaken-Gaming)**: the [FNaF-ARchive](https://github.com/Forsaken-Gaming/FNaF-ARchive) preservation builds and the public asset CDN.
- [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) (analysis), [uber-apk-signer](https://github.com/patrickfav/uber-apk-signer), [Termux](https://termux.dev).
