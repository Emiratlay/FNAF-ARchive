"""
End-to-end test of the offline game logic (no phone needed).
Plays a whole session against game.py with a throw-away save and prints OK/FAIL per step.

Needs cdn/8.0.0/Masterdata/800 (python download_cdn.py).
Usage:  python test_offline.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game  # noqa: E402

game.STATE_FILE = os.path.join(os.path.dirname(game.STATE_FILE), "_test_offline.json")
game.SEND_TRAVEL_SECONDS = 0
failures = []


def cs(fn, **params):
    _, r = game.handle("/Client/ExecuteCloudScript", {"FunctionName": fn, "FunctionParameter": params})
    return r["data"]["FunctionResult"]["scriptData"]


def pf(path, **req):
    return game.handle(path, req)[1]


def state():
    return game.load_state()


def check(name, cond, extra=""):
    print(("OK   " if cond else "FAIL ") + name + ("  " + str(extra) if extra != "" else ""))
    if not cond:
        failures.append(name)


def main():
    if os.path.exists(game.STATE_FILE):
        os.remove(game.STATE_FILE)
    random.seed(3)
    pf("/Client/LoginWithCustomID", TitleId="E6771")
    cs("AWARD_UNIQUE_REWARDS", cpuId="BareEndo_FTUE")
    cs("SET_FEATURE_FLAGS", entryObject=dict({k: 1 for k in game.FLAG_MAP}, tutorialKey="FTUE"))

    # Drops are rolled at spawn time and paid out on a win.
    dropped = None
    for _ in range(500):
        for eid, e in (cs("REQUEST_ENTITIES_V8", uiLocation="map").get("NewAnimatronicEntities") or {}).items():
            r = e["rewardsV3"]
            if r["ModRewards"] or r["CPURewards"] or r["AnimatronicRewards"]:
                dropped = (eid, r)
            else:
                cs("ATTACK_MODE_LOST_V2", entityId=eid)
        if dropped:
            break
    check("drop rolled at spawn", dropped is not None, dropped and dropped[1])
    win = cs("AWARD_ENTITY_REWARDS_V2", entityId=dropped[0])
    check("win returns the changed inventory", any(k in win for k in ("ModInventory", "CPUInventory", "Inventory")),
          [k for k in win if k not in ("ProfileRead", "ProfileWrite")])

    # Remnant: server-side nodes, colour decides the amount.
    motes = []
    for i in range(30):
        for node in cs("ESSENCE_NODE_SPAWN_V2", objectTypes=["ForcedSpawn_%d" % i]).get("EssencesToSpawn", []):
            motes.append((node["type"], node["motes"]))
    check("remnant nodes spawned", motes, motes[:2])
    values = {t["NodeType"]["Logical"]: (t.get("MoteOverrides") or {}).get("SpawnBehavior", {}).get("EssencePerMote")
              for t in game.md("ESSENCE_TYPES_DATA")}
    expected = sum(values[c] * len(m) for c, m in motes)
    before = state()["Currency"]["ESSENCE"]
    after = cs("ESSENCE_NODE_COLLECT_V2", motesCollectedList=[x for _, m in motes for x in m])["Currency"]["ESSENCE"]
    check("remnant amount by colour", after - before == expected, (before, after, expected))
    check("remnant milestone message",
          any(m["Logical"] == "Remnant-Debuff" for m in cs("ESSENCE_LEVEL_UP")["Inbox"].values()))

    # Store
    s = state()
    s["Currency"].update({"PARTS": 5000, "FAZ_TOKENS": 5000})
    game.save_state(s)
    for item, cur, price in [("SalvageScanner", "PA", 60), ("ExtraBattery", "FC", 100), ("Pack_Chica", "FC", 650),
                             ("Endoskeleton_01", "FC", 300), ("Fazcoin_Roll_hardcurrency_03", "PA", 250),
                             ("Lure_Foxy", "FC", 300)]:
        r = pf("/Client/PurchaseItem", ItemId=item, VirtualCurrency=cur, Price=price, StoreId="Default",
               CatalogVersion="Test")
        check("buy " + item, r.get("code") == 200,
              r.get("errorMessage") or r["data"]["Items"][0].get("BundleContents"))
    r = pf("/Client/PurchaseItem", ItemId="Pack_Chica", VirtualCurrency="FC", Price=650)
    check("one-time pack cannot be bought twice", r.get("error") == "ItemNotFound")
    s = state()
    check("store results", s["PlayerDeviceData"]["purchased"].get("SalvageScanner") == 1
          and s["Inventory"]["Chica"]["PlushSuit"] == 1 and len(s["Warehouse"]) == 2,
          (s["Currency"], s["PlayerDeviceData"]["purchased"], len(s["Warehouse"])))
    check("owned goods", len(cs("GET_OWNED_GOODS")["Goods"]) >= 5)

    # Devices
    d = cs("ACTIVATE_DEVICE", deviceConfigId="SalvageScanner")["PlayerDeviceData"]
    check("salvage scanner active", d["active"]["SalvageScanner"])
    did = list(d["active"]["SalvageScanner"])[0]
    s = state()
    s["PlayerDeviceData"]["purchased"]["FriendOrFoeTransponder"] = 1
    game.save_state(s)
    t = cs("ACTIVATE_DEVICE", deviceConfigId="FriendOrFoeTransponder")["PlayerDeviceData"]["active"]["FriendOrFoeTransponder"]
    ts = list(t.values())[0]["deviceState"]["expirationTimeStamp"]
    import time as _t
    check("transponder expiry in milliseconds (3 days)", abs(ts - (_t.time() + 259200) * 1000) < 60000, ts)
    s = state()
    for v in s["PlayerDeviceData"]["active"]["FriendOrFoeTransponder"].values():
        v["deviceState"]["expirationTimeStamp"] = (_t.time() - 5) * 1000
    game.save_state(s)
    cs("GET_PLAYER_DATA")
    check("expired transponder is removed", not state()["PlayerDeviceData"]["active"]["FriendOrFoeTransponder"])
    check("device expired", not cs("EXPIRE_DEVICE", activeDeviceId=did)["PlayerDeviceData"]["active"]["SalvageScanner"])
    cs("ACTIVATE_DEVICE", deviceConfigId="Lure_Foxy")
    s = state()
    check("lure queues Foxy", s["Incoming"] and s["Incoming"][0]["entity"]["animatronicConfigId"] == "Foxy")
    s["Incoming"][0]["at"] = 0
    game.save_state(s)
    new = cs("REQUEST_ENTITIES_V8", uiLocation="map").get("NewAnimatronicEntities", {})
    check("lured Foxy arrives", any(e["animatronicConfigId"] == "Foxy" and e["originData"]["animatronicOrigin"] == 1
                                    for e in new.values()))

    # Radio jammer: 2 hours, millisecond expiry
    import time as _tj
    s = state()
    s["PlayerDeviceData"]["purchased"]["RadioJammer"] = 1
    game.save_state(s)
    j = cs("ACTIVATE_DEVICE", deviceConfigId="RadioJammer")["PlayerDeviceData"]["active"]["RadioJammer"]
    jts = list(j.values())[0]["deviceState"]["expirationTimeStamp"]
    check("radio jammer lasts 2 hours (ms)", abs(jts - (_tj.time() + 7200) * 1000) < 60000, jts)
    s = state()
    s["PlayerDeviceData"]["active"]["RadioJammer"] = {}
    game.save_state(s)

    # Independent drops: over many spawns every drop kind appears, sometimes together
    import collections as _c
    kinds = _c.Counter()
    for _ in range(3000):
        d = game.roll_drops("FreddyFazbear_Insane")
        n = sum(1 for k in ("AnimatronicRewards", "CPURewards", "ModRewards") if d[k])
        for k in ("AnimatronicRewards", "CPURewards", "ModRewards"):
            if d[k]:
                kinds[k] += 1
        if n >= 2:
            kinds["together"] += 1
    check("drops are independent (suit, CPU, mod, combined)", all(kinds[k] for k in
          ("AnimatronicRewards", "CPURewards", "ModRewards", "together")), dict(kinds))

    # Express delivery of an animatronic on the map
    s = state()
    s["Currency"]["FAZ_TOKENS"] = 100
    game.save_state(s)
    on_map = next(eid for eid, e in state()["Entities"].items() if e["originData"]["animatronicOrigin"] in (0, 1))
    r = cs("EXPRESS_DELIVERY", entityId=on_map)
    upd = r.get("UpdateAnimatronicEntities")
    check("express delivery: list with the updated animatronic",
          isinstance(upd, list) and upd and upd[0]["entityId"] == on_map
          and upd[0]["stateData"]["expressDelivery"] is True and upd[0]["stateData"]["animatronicState"] == 2
          and r["Currency"]["FAZ_TOKENS"] == 50, (r["Currency"], upd and upd[0]["stateData"]))

    # Salvage scanner: parts bonus on a win, uses a charge
    s = state()
    s["PlayerDeviceData"]["purchased"]["SalvageScanner"] = 1
    s["StreakData"] = {"CurrentStreak": 0, "BestStreak": 50}   # no new-best bonus in this check
    game.save_state(s)
    cs("ACTIVATE_DEVICE", deviceConfigId="SalvageScanner")
    s = state()
    target = next(eid for eid, e in s["Entities"].items() if (e["rewardsV3"].get("CurrencyRewards") or {}).get("PARTS"))
    base_parts = s["Entities"][target]["rewardsV3"]["CurrencyRewards"]["PARTS"]
    before = s["Currency"]["PARTS"]
    w = cs("AWARD_ENTITY_REWARDS_V2", entityId=target)
    check("salvage scanner bonus", w["Currency"]["PARTS"] - before == int(round(base_parts * 1.25))
          and not game.active_charges(state(), "SalvageScanner"), (base_parts, w["Currency"]["PARTS"] - before))

    # EMF meter: charges used by remnant spawns
    s = state()
    s["PlayerDeviceData"]["purchased"]["EMFMeter"] = 1
    game.save_state(s)
    cs("ACTIVATE_DEVICE", deviceConfigId="EMFMeter")
    start = game.active_charges(state(), "EMFMeter")
    for i in range(20):
        cs("ESSENCE_NODE_SPAWN_V2", objectTypes=["EMF_%d" % i])
    check("EMF meter uses charges", start == 10 and game.active_charges(state(), "EMFMeter") < start,
          (start, game.active_charges(state(), "EMFMeter")))

    # Custom CPU with its own attack profile, spawning in the wild
    import json
    custom_file = game.CUSTOM_FILE
    game.CUSTOM_FILE = os.path.join(os.path.dirname(game.STATE_FILE), "_test_custom.json")
    cpu = dict(game.md_by_logical("CPU_DATA")["ToyBonnie"], Logical="Custom_Test_cpu", AttackProfile="Custom_Test_cpu",
               SpawnByStreak={"RankRangeByBestStreak": {"Min": 1, "Max": 1000},
                              "RankRangeByCurrentStreak": {"Min": 0, "Max": 1000}})
    attack = dict(next(a for a in game.md("ATTACK_DATA") if a["Logical"] == "ToyBonnie"), Logical="Custom_Test_cpu")
    with open(game.CUSTOM_FILE, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "cpus": [cpu], "attacks": [attack], "loc": []}, f)
    check("custom CPU and attack profile in master data",
          game.md_version() == game.BASE_MD_VERSION + 1 and any(c["Logical"] == "Custom_Test_cpu" for c in game.md("CPU_DATA"))
          and any(a["Logical"] == "Custom_Test_cpu" for a in game.md("ATTACK_DATA")))
    check("custom CPU can spawn", "Custom_Test_cpu" in game.spawn_candidates(state()))
    os.remove(game.CUSTOM_FILE)
    game.CUSTOM_FILE = custom_file
    game._md.clear()

    # Streak progression: bonus parts and endo slots
    s = state()
    s["StreakData"] = {"CurrentStreak": 3, "BestStreak": 3}
    s["UnlockedEndoskeletonSlots"] = 1
    game.save_state(s)
    before_parts = state()["Currency"]["PARTS"]
    eid = next(iter(state()["Entities"]), None)
    if eid is None:
        e = game.make_entity(state(), "Chica_Basic", origin=0)
        s = state(); s["Entities"][e["entityId"]] = e; game.save_state(s); eid = e["entityId"]
    reward_parts = (state()["Entities"][eid]["rewardsV3"].get("CurrencyRewards") or {}).get("PARTS", 0)
    w = cs("AWARD_ENTITY_REWARDS_V2", entityId=eid)
    check("new best streak 4 pays bonus parts (25)", w["Currency"]["PARTS"] - before_parts >= 25 + reward_parts - 1,
          (w["Currency"]["PARTS"] - before_parts, reward_parts))
    s = state()
    s["StreakData"] = {"CurrentStreak": 4, "BestStreak": 4}
    game.save_state(s)
    e = game.make_entity(state(), "Chica_Basic", origin=0)
    s = state(); s["Entities"][e["entityId"]] = e; game.save_state(s)
    w = cs("AWARD_ENTITY_REWARDS_V2", entityId=e["entityId"])
    check("streak 5 unlocks a second endo slot", state()["UnlockedEndoskeletonSlots"] == 2
          and len(w["WarehouseDataV2"]) >= 2 + state().get("PurchasedEndoskeletonSlots", 0) - 0,
          (state()["UnlockedEndoskeletonSlots"], len(w["WarehouseDataV2"])))

    # Workshop
    s = state()
    mod = next(iter(s["ModInventory"]), "Map_Sub_02")
    s["ModInventory"][mod] = 2
    s["CPUInventory"]["Foxy"] = 1
    game.save_state(s)
    w = cs("SET_ENDOSKELETON_CONFIG_V2", slot=0, config={"mods": [mod], "cpu": "Foxy", "plushSuit": "Chica", "essence": 1})
    check("equip CPU + suit + mod + remnant",
          w["WarehouseDataV2"][0]["endoskeleton"] == {"cpu": "Foxy", "plushSuit": "Chica", "mods": [mod], "essence": 1})
    s = state()
    s["Warehouse"][0]["wearAndTear"] = 60
    game.save_state(s)
    check("repair", cs("REPAIR_ANIMATRONIC", slotId=0, cost=8)["WarehouseDataV2"][0]["wearAndTear"] == 100)
    check("sell mod", cs("SELL_MODS", mods={mod: 1})["ModInventory"][mod] == 1)

    # Scavenging
    w = cs("START_SCAVENGE_APPOINTMENT", slotId=1, appointmentId="Scavenge60")
    check("scavenge start on slot 2", w["WarehouseDataV2"][1]["status"] == "ScavengeAppointment")
    c = cs("COLLECT_SCAVENGE_APPOINTMENT", slotId=1)
    check("scavenge collect", c["WarehouseDataV2"][1]["status"] == "Available" and "RewardsV2" in c, c["RewardsV2"])
    # Scavenge loot variety over many trips
    import collections
    seen = collections.Counter()
    stars = collections.Counter()
    mods = game.md_by_logical_key("MODS_DATA", "ModLogical")
    for appt in ("Scavenge30", "Scavenge240"):
        for _ in range(150):
            rw, devs, _w = game.scavenge_rewards(appt)
            if rw["CurrencyRewards"].get("PARTS"):
                seen["parts"] += 1
            if rw["CurrencyRewards"].get("FAZ_TOKENS"):
                seen["faz-coins"] += 1
            if devs:
                seen["device"] += 1
            if rw["CPURewards"]:
                seen["cpu"] += 1
            for m in rw["ModRewards"]:
                seen["mod"] += 1
                stars[(appt, mods[m]["Stars"])] += 1
    check("scavenge gives parts, mods, Faz-Coins and devices",
          seen["parts"] == 300 and seen["mod"] and seen["faz-coins"] and seen["device"], dict(seen))
    low = sum(n for (a, st), n in stars.items() if a == "Scavenge30" and st == 1)
    high30 = sum(n for (a, st), n in stars.items() if a == "Scavenge30" and st > 1)
    check("longer scavenges give higher-star mods",
          low > high30 * 5 and any(st > 1 for (a, st) in stars if a == "Scavenge240"), dict(stars))

    cs("START_SCAVENGE_APPOINTMENT", slotId=1, appointmentId="Scavenge30")
    r = cs("RECALL_SCAVENGE_APPOINTMENT", slotId=1)
    check("scavenge recall", r["WarehouseDataV2"][1]["status"] == "Available" and r["ScavengeRecall"][0])

    # Sending an animatronic to yourself
    w = cs("SEND_ANIMATRONIC_ATTACK_V2", slotId=0, userId=state()["PlayFabId"])
    check("send to yourself", w["WarehouseDataV2"][0]["status"] == "Sent")
    new = cs("REQUEST_ENTITIES_V8", uiLocation="map").get("NewAnimatronicEntities", {})
    sent = [e for e in new.values() if e["originData"]["animatronicOrigin"] == 4]
    check("it arrives as an attacker with your CPU",
          sent and sent[0]["endoskeleton"]["cpu"] == "Foxy" and state()["Warehouse"][0]["status"] == "Attacking")
    cs("AWARD_ENTITY_REWARDS_V2", entityId=sent[0]["entityId"])
    check("endo back in the workshop afterwards", state()["Warehouse"][0]["status"] == "Available")
    cs("SEND_ANIMATRONIC_ATTACK_V2", slotId=0, userId="someone")
    check("recall a sent attack", cs("RECALL_ATTACKING_ANIMATRONIC", slotId=0)["WarehouseDataV2"][0]["status"] == "Available")

    # Friends list holds "you", so the Send Animatronic screen has a target
    friends = cs("GET_PLAYER_FRIENDS")["friendsList"]
    check("friends list has yourself", list(friends.values())[0]["userId"] == game.SELF_FRIEND_ID, friends)
    cs("SEND_ANIMATRONIC_ATTACK_V2", slotId=0, userId=game.SELF_FRIEND_ID)
    new = cs("REQUEST_ENTITIES_V8", uiLocation="map").get("NewAnimatronicEntities", {})
    check("sending to the friend entry comes back to you",
          any(e["originData"]["animatronicOrigin"] == 4 for e in new.values()))
    cs("RECALL_ATTACKING_ANIMATRONIC", slotId=0)

    # Shadow Bonnie lure: in the store, master data and activation
    check("Shadow Bonnie lure in master data",
          any(d.get("DeviceLogical") == game.SB_LURE for d in game.md("DEVICES_DATA"))
          and any(p.get("PurchasableLogical") == game.SB_LURE for p in game.md("STORE_DATA"))
          and any(l["ID"] == "device_name_" + game.SB_LURE for l in game.md("LOC_DATA")))
    items = [i["ItemId"] for st in cs("GET_STORE_ITEMS_V2")["StoreItems"]["Stores"] for i in st["Items"]]
    check("Shadow Bonnie lure in the store list", game.SB_LURE in items)
    s = state()
    s["Currency"]["FAZ_TOKENS"] = 1000
    game.save_state(s)
    r = pf("/Client/PurchaseItem", ItemId=game.SB_LURE, VirtualCurrency="FC", Price=game.SB_LURE_PRICE)
    check("buy Shadow Bonnie lure", r.get("code") == 200 and state()["PlayerDeviceData"]["purchased"].get(game.SB_LURE) == 3,
          r.get("errorMessage"))
    cs("ACTIVATE_DEVICE", deviceConfigId=game.SB_LURE)
    s = state()
    for i in s["Incoming"]:
        i["at"] = 0
    game.save_state(s)
    new = cs("REQUEST_ENTITIES_V8", uiLocation="map").get("NewAnimatronicEntities", {})
    sbs = [e for e in new.values() if e["animatronicConfigId"].startswith("ShadowBonnie")]
    check("lure brings Shadow Bonnie (Easy)", sbs and sbs[0]["animatronicConfigId"] == "ShadowBonnie_Easy"
          and sbs[0]["originData"]["animatronicOrigin"] == 2, [e["animatronicConfigId"] for e in new.values()])
    cs("AWARD_ENTITY_REWARDS_V2", entityId=sbs[0]["entityId"])
    cs("ACTIVATE_DEVICE", deviceConfigId=game.SB_LURE)
    s = state()
    nxt = [i["entity"]["animatronicConfigId"] for i in s["Incoming"]]
    check("next lure is harder (Medium)", "ShadowBonnie_Medium" in nxt, nxt)
    s["Incoming"] = []
    game.save_state(s)

    # Shadow Bonnie (remnant threat path)
    sb = list(cs("START_ESSENCE_ENCOUNTER_V3")["NewAnimatronicEntities"].values())[0]
    check("Shadow Bonnie encounter (Medium after one Easy win)", sb["animatronicConfigId"] == "ShadowBonnie_Medium")
    cs("AWARD_ENTITY_REWARDS_V2", entityId=sb["entityId"])
    check("Shadow Bonnie defeats counted",
          state()["PlayerStatsData"]["plushSuitDefeatDataList"]["ShadowBonnie"]["ShadowBonnie_Medium"] == 1)

    # Daily challenges
    dc = cs("REQUEST_ROLLOVER_DATA")["PlayerDailyChallengeData"]
    first = dc["dailyChallenges"][0]["dailyChallengeLogical"]
    d = cs("CHANGE_SINGLE_DAILY_CHALLENGE", dailyChallengeToChangeLogical=first, adWatched=0)
    check("change a daily challenge", d["PlayerDailyChallengeData"]["dailyChallenges"][0]["dailyChallengeLogical"] != first)
    s = state()
    for c in s["DailyChallenges"]["dailyChallenges"]:
        c["progress"] = c["completionGoal"]
    game.save_state(s)
    d = cs("COLLECT_DAILY_CHALLENGE_REWARDS")
    check("collect daily reward", d["PlayerDailyChallengeData"]["state"] == "COLLECTED"
          and d.get("DailyChallengeRewardsLogical"), d.get("DailyChallengeRewardsLogical"))
    check("daily reward only once", "DailyChallengeRewardsLogical" not in cs("COLLECT_DAILY_CHALLENGE_REWARDS"))

    # Profile
    check("avatar", cs("SAVE_AVATAR", avatarId="female")["PlayerProfile"]["avatarId"] == "female")
    code = cs("GENERATE_NEW_FRIENDCODE")["friendCode"]
    check("friend code lookup", cs("LOOKUP_FRIENDCODE", friendCode=code)["lookupFriendCodeResponse"] == "userTriedToFriendSelf")
    check("display name", pf("/Client/UpdateUserTitleDisplayName", DisplayName="Freddy")["data"]["DisplayName"] == "Freddy"
          and cs("GET_PLAYER_DATA")["PlayerProfile"]["displayName"] == "Freddy")

    os.remove(game.STATE_FILE)
    print("\n%d failed" % len(failures) if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
