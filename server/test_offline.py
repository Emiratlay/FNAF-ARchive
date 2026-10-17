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
    check("device expired", not cs("EXPIRE_DEVICE", activeDeviceId=did)["PlayerDeviceData"]["active"]["SalvageScanner"])
    cs("ACTIVATE_DEVICE", deviceConfigId="Lure_Foxy")
    s = state()
    check("lure queues Foxy", s["Incoming"] and s["Incoming"][0]["entity"]["animatronicConfigId"] == "Foxy")
    s["Incoming"][0]["at"] = 0
    game.save_state(s)
    new = cs("REQUEST_ENTITIES_V8", uiLocation="map").get("NewAnimatronicEntities", {})
    check("lured Foxy arrives", any(e["animatronicConfigId"] == "Foxy" and e["originData"]["animatronicOrigin"] == 1
                                    for e in new.values()))

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

    # Shadow Bonnie
    sb = list(cs("START_ESSENCE_ENCOUNTER_V3")["NewAnimatronicEntities"].values())[0]
    check("Shadow Bonnie encounter", sb["animatronicConfigId"] == "ShadowBonnie_Easy")
    cs("AWARD_ENTITY_REWARDS_V2", entityId=sb["entityId"])
    check("Shadow Bonnie defeat counted",
          state()["PlayerStatsData"]["plushSuitDefeatDataList"]["ShadowBonnie"]["ShadowBonnie_Easy"] == 1)

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
