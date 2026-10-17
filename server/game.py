"""
Offline game logic for FNAF AR 8.0.0 (FNaF ARchive build).

Emulates the CloudScript functions of the ARchive PlayFab server locally.
Rules (spawns, rewards, scavenging, inbox) are read from the game's own master data
in cdn/8.0.0/Masterdata/800. Response shapes come from templates/ (sanitized real
responses). The player save lives in save/state.json.

handle(path, request) -> (status, response), or None for calls without logic
(server.py then falls back to replaying captures, if any).
"""
import copy
import json
import os
import random
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates")
STATE_FILE = os.path.join(HERE, "save", "state.json")
MASTERDATA = os.path.join(HERE, "cdn", "8.0.0", "Masterdata", "800")
# Custom content created by the editor app (mod chips, skins, texts).
CUSTOM_FILE = os.path.join(HERE, "custom", "custom.json")
BASE_MD_VERSION = 800
# custom.json section -> master data file it is appended to
CUSTOM_SECTIONS = {"mods": "MODS_DATA", "plushsuits": "PLUSHSUIT_DATA", "cpus": "CPU_DATA",
                   "attacks": "ATTACK_DATA", "loc": "LOC_DATA"}

# Max wild animatronics at once, and spawn chance per REQUEST_ENTITIES poll (~every 11 s).
MAX_WILD = 3
SPAWN_CHANCE = 0.35
FTUE_FAZ_TOKENS = 150

lock = threading.RLock()
_md = {}
_tpl = {}


# ---------------------------------------------------------------- helpers

def now_ms():
    return int(time.time() * 1000)


def custom():
    try:
        with open(CUSTOM_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def md_version():
    """Master data version; it goes up whenever custom content changes so the game re-downloads."""
    return BASE_MD_VERSION + int(custom().get("version", 0) or 0)


def md(name):
    ver = md_version()
    if _md.get(name, (None,))[0] != ver:
        with open(os.path.join(MASTERDATA, name), encoding="utf-8") as f:
            entries = json.load(f)["Entries"]
        c = custom()
        for section, file_name in CUSTOM_SECTIONS.items():
            if file_name == name:
                entries = entries + list(c.get(section) or [])
        _md[name] = (ver, entries)
    return _md[name][1]


def masterdata_bytes(name):
    """Master data file as served to the game (original + custom content)."""
    if not os.path.isfile(os.path.join(MASTERDATA, name)):
        return None
    return json.dumps({"Entries": md(name)}, ensure_ascii=False).encode("utf-8")


def md_by_logical(name):
    return {e["Logical"]: e for e in md(name) if "Logical" in e}


def _load_template(fn):
    if fn not in _tpl:
        try:
            with open(os.path.join(TEMPLATES, fn + ".json"), encoding="utf-8") as f:
                _tpl[fn] = json.load(f)
        except (OSError, ValueError):
            _tpl[fn] = {}
    return _tpl[fn]


def template(fn):
    """scriptData of a real response for this function (shape template)."""
    return copy.deepcopy(_load_template(fn).get("scriptData") or {})


def result_defaults(fn):
    """Top-level FunctionResult fields the real server adds (e.g. newPlayer). The game
    throws KeyNotFoundException and hangs if they are missing."""
    return copy.deepcopy(_load_template(fn).get("resultExtras") or {})


def rand_range(r, default=0):
    if not isinstance(r, dict):
        return default
    lo, hi = r.get("Min", default), r.get("Max", r.get("Min", default))
    return random.randint(int(lo), int(hi)) if isinstance(lo, int) and isinstance(hi, int) else lo


def deep_merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)


def hexid():
    return uuid.uuid4().hex[:16].upper()


# ---------------------------------------------------------------- player state

def new_state():
    pid, tid = hexid(), hexid()
    t = template("GET_PLAYER_DATA")
    return {
        "PlayFabId": pid,
        "TitlePlayerId": tid,
        "SessionTicket": "%s-%s-%s" % (pid, hexid(), uuid.uuid4().hex),
        "friendCode": uuid.uuid4().hex[:10].upper(),
        "Currency": {"PARTS": 0, "ESSENCE": 0, "FAZ_TOKENS": 0},
        "Inventory": t.get("Inventory") or {"BareEndo": {"Auto": 0, "Common": 0, "ControlKeys": 0,
                                                         "PlushSuit": 1, "Rare": 0, "Uncommon": 0}},
        "CPUInventory": t.get("CPUInventory") or {"BareEndo": 1},
        "ModInventory": {},
        "PlayerDeviceData": t.get("PlayerDeviceData") or {"active": {}, "pending": [], "purchased": {}},
        "Inbox": {},
        "PlayerTutorialData": t.get("PlayerTutorialData") or {"Entries": []},
        "PlayerFeatureFlags": t.get("PlayerFeatureFlags") or {"flags": []},
        "PlayerStatsData": t.get("PlayerStatsData") or {"totalEssence": 0, "plushSuitDefeatDataList": {}},
        "PlayerAlertData": t.get("PlayerAlertData") or {},
        "StreakData": {"CurrentStreak": 0, "BestStreak": 0},
        "UnlockedEndoskeletonSlots": t.get("UnlockedEndoskeletonSlots", 1),
        "PurchasedEndoskeletonSlots": t.get("PurchasedEndoskeletonSlots", 0),
        "Goods": [],
        "Entities": {},
        "Warehouse": template("GET_WAREHOUSE_DATA_V2").get("WarehouseDataV2") or [
            {"status": "Available", "lastCommand": 0, "entityId": "", "wearAndTear": 100,
             "endoskeleton": {"cpu": "BareEndo", "plushSuit": "BareEndo", "mods": [], "essence": 0},
             "receiverId": "", "appointmentId": ""}],
        "DailyChallenges": None,
        "FtueRewarded": False,
    }


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        s = new_state()
        save_state(s)
        return s


def save_state(s):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def profile(s):
    name = s.get("DisplayName") or s["PlayFabId"]
    return {"avatarId": s.get("AvatarId", "default"), "displayName": name, "fazPassInviteTokenList": [],
            "inviteTokenList": [], "userId": s["PlayFabId"], "userName": name}


def migrate(s):
    """Adds fields introduced after a save was created."""
    s.setdefault("Goods", [])
    s.setdefault("Incoming", [])
    s.setdefault("ModInventory", {})
    s.setdefault("CPUInventory", {"BareEndo": 1})
    s.setdefault("Inventory", {})
    s.setdefault("Currency", {"PARTS": 0, "ESSENCE": 0, "FAZ_TOKENS": 0})
    dev = s.setdefault("PlayerDeviceData", {})
    dev.setdefault("active", {})
    dev.setdefault("pending", [])
    dev.setdefault("purchased", {})
    stats = s.setdefault("PlayerStatsData", {})
    stats.setdefault("totalEssence", 0)
    stats.setdefault("plushSuitDefeatDataList", {"ShadowBonnie": {
        "ShadowBonnie_Easy": 0, "ShadowBonnie_Medium": 0, "ShadowBonnie_Hard": 0, "ShadowBonnie_Insane": 0}})


# ---------------------------------------------------------------- inventory

EMPTY_SUIT = {"Auto": 0, "Common": 0, "ControlKeys": 0, "PlushSuit": 0, "Rare": 0, "Uncommon": 0}


def add_good(s, item_id, item_class, uses=None):
    """Mirror of the PlayFab inventory the real server keeps (returned by GET_OWNED_GOODS)."""
    for g in s["Goods"]:
        if g["ItemId"] == item_id and uses is not None and "RemainingUses" in g:
            g["RemainingUses"] += uses
            return g
    g = {"ItemId": item_id, "ItemInstanceId": hexid(), "ItemClass": item_class,
         "PurchaseDate": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
         "CatalogVersion": "Test", "DisplayName": "", "UnitPrice": 0}
    if uses is not None:
        g["RemainingUses"] = uses
    s["Goods"].append(g)
    return g


def give_suit(s, suit):
    inv = s["Inventory"].setdefault(suit, dict(EMPTY_SUIT))
    inv["PlushSuit"] = max(1, inv.get("PlushSuit", 0))
    add_good(s, "PlushSuit_" + suit, "PlushSuit")


def give_cpu(s, cpu, n=1):
    s["CPUInventory"][cpu] = s["CPUInventory"].get(cpu, 0) + n


def give_mod(s, mod, n=1):
    s["ModInventory"][mod] = s["ModInventory"].get(mod, 0) + n
    add_good(s, "Mod_" + mod, "Mod", n)
    progress(s, "CollectMods", amount=n)


def give_device(s, device, n=1):
    purchased = s["PlayerDeviceData"]["purchased"]
    purchased[device] = purchased.get(device, 0) + n
    add_good(s, "Device_" + device, "Device", n)


def apply_rewards(s, rewards):
    """Applies a rewards dict (AnimatronicRewards/CPURewards/ModRewards/CurrencyRewards) and
    returns the scriptData keys the client needs to refresh."""
    out = {}
    for suit, items in (rewards.get("AnimatronicRewards") or {}).items():
        if (items or {}).get("PlushSuit"):
            give_suit(s, suit)
            out["Inventory"] = s["Inventory"]
    for cpu, n in (rewards.get("CPURewards") or {}).items():
        give_cpu(s, cpu, n)
        out["CPUInventory"] = s["CPUInventory"]
    for mod, n in (rewards.get("ModRewards") or {}).items():
        give_mod(s, mod, n)
        out["ModInventory"] = s["ModInventory"]
    for cur, n in (rewards.get("CurrencyRewards") or {}).items():
        add_currency(s, cur, n)
        out["Currency"] = s["Currency"]
    return out


def base_animatronic(cpu_id):
    """FreddyFazbear_Haywire -> FreddyFazbear: the CPU and plush suit a defeated animatronic drops."""
    cpu = md_by_logical("CPU_DATA").get(cpu_id, {})
    return cpu.get("PlushSuitRef") or cpu_id.split("_")[0]


def pick_mod(rank):
    """Random mod weighted by DropWeight; low-rank animatronics drop low-star mods."""
    max_stars = 1 if (rank or 1) <= 2 else 2 if rank <= 6 else 3
    pool = [m for m in md("MODS_DATA") if (m.get("DropWeight") or 0) > 0 and (m.get("Stars") or 1) <= max_stars]
    if not pool:
        return None
    return random.choices(pool, weights=[m["DropWeight"] for m in pool])[0]["ModLogical"]


def roll_drops(cpu_id, chance_scale=1.0):
    """Item drops decided at spawn time, like the real server (stored in rewardsV3)."""
    cpu = md_by_logical("CPU_DATA").get(cpu_id, {})
    cfg = (cpu.get("Rewards") or {}).get("WanderingAnimatronics") or {}
    base = base_animatronic(cpu_id)
    drops = {"AnimatronicRewards": {}, "CPURewards": {}, "ModRewards": {}}
    if random.random() < (cfg.get("PlushSuitDropChance") or 0) * chance_scale:
        drops["AnimatronicRewards"][base] = {"PlushSuit": 1}
    elif random.random() < (cfg.get("CPUDropChance") or 0) * chance_scale:
        # Custom CPUs drop themselves; stock variants (Chica_Haywire) drop their main CPU (Chica).
        cpu_reward = cpu_id if cpu_id.startswith("Custom_") else base
        if cpu_reward in md_by_logical("CPU_DATA"):
            drops["CPURewards"][cpu_reward] = 1
    elif random.random() < (cfg.get("ModDropChance") or 0) * chance_scale:
        mod = pick_mod(cpu.get("Rank"))
        if mod:
            drops["ModRewards"][mod] = 1
    return drops


# ---------------------------------------------------------------- animatronics

def make_entity(s, cpu_id, origin, plush=None, wear=None):
    """origin: 0 = wild spawn, 3 = own endo sent scavenging, 5 = tutorial/transient."""
    cpu = md_by_logical("CPU_DATA").get(cpu_id, {})
    plush = plush or cpu.get("PlushSuitRef") or cpu_id.split("_")[0]
    rewards = (cpu.get("Rewards") or {}).get("WanderingAnimatronics") or {}
    nodes = cpu.get("MapNodes") or {}
    ts = now_ms()
    parts = rand_range(rewards.get("Parts"), 0)
    drops = roll_drops(cpu_id) if origin in (0, 1, 2) else {"AnimatronicRewards": {}, "CPURewards": {}, "ModRewards": {}}
    return {
        "ScavengingData": {"NextPoint": {"name": "", "id": "", "type": 0}, "TimeStamp": 0},
        "animatronicConfigId": cpu_id,
        "attackStateData": {"attackSequenceComplete": False, "encounterStartTime": 0},
        "distanceFromPlayerData": {"distance": 0, "initialized": False, "minDistance": 0},
        "endoskeleton": {"cpu": cpu_id, "plushSuit": plush, "mods": [], "essence": 0},
        "entityId": "%s_%d" % (cpu_id, ts),
        "geoPositionData": {"geoPosition": {"x": 0, "y": 0}},
        "malfunctioningData": {"isMalfunctioning": False},
        "moveStateData": {"endNode": {"id": "", "name": "", "type": 0},
                          "maxNodes": rand_range(nodes.get("NodePathMin"), 0) if origin == 0 else 0,
                          "nodeCounter": 0,
                          "nodeTravelTime": rand_range(nodes.get("NodeTravelTime"), 0) if origin == 0 else 0,
                          "startNode": {"id": "", "name": "", "type": 0}, "timeElapsed": 0},
        "originData": {"animatronicOrigin": origin},
        "rewardsV3": {"AnimatronicRewards": drops["AnimatronicRewards"], "CPURewards": drops["CPURewards"],
                      "CurrencyRewards": {"PARTS": parts} if parts else {},
                      "EssenceOnLose": rand_range(rewards.get("EssenceOnLose"), 0) if origin in (0, 1) else 0,
                      "ModRewards": drops["ModRewards"]},
        "owner": s["PlayFabId"],
        "spawnTime": ts,
        "stalkingTimerData": {"timeRemainingInitialized": False, "timeRemaining": 0,
                              "switchbackTimeRemaining": 0, "direction": 0},
        "stateData": {"animatronicState": 0, "expressDelivery": False},
        "updateTimerData": {"accumulatedDeltaTime": 0, "nextUpdateTimer": ts, "lastUpdateTimestamp": 0},
        "wearAndTear": cpu.get("Condition", 100) if wear is None else wear,
    }


def in_range(value, r, default_min):
    lo = r.get("Min", default_min)
    hi = r.get("Max", 10 ** 9)
    if lo == -1 and hi == -1:
        return False
    return lo <= value <= hi


def spawn_candidates(s):
    """CPUs allowed to spawn for the current/best win streak (CPU_DATA SpawnByStreak)."""
    best = s["StreakData"]["BestStreak"]
    cur = s["StreakData"]["CurrentStreak"]
    out = []
    for cpu in md("CPU_DATA"):
        sbs = cpu.get("SpawnByStreak") or {}
        if (cpu.get("Status") or {}).get("LiveState") != "State_Active":
            continue
        if not (cpu.get("Rewards") or {}).get("WanderingAnimatronics"):
            continue
        if in_range(max(best, 1), sbs.get("RankRangeByBestStreak") or {}, 1) and \
                in_range(cur, sbs.get("RankRangeByCurrentStreak") or {}, 0):
            out.append(cpu["Logical"])
    return out


def spawns_allowed(s):
    """No wild spawns while a tutorial has spawns switched off."""
    for f in s["PlayerFeatureFlags"].get("flags", []):
        if f.get("TutorialKey") and f.get("SpawnState", 0) != 0:
            return False
    return True


def wild_count(s):
    return sum(1 for e in s["Entities"].values() if (e.get("originData") or {}).get("animatronicOrigin") == 0)


# ---------------------------------------------------------------- rewards and daily challenges

def daily(s):
    dc = s.get("DailyChallenges")
    if not dc or dc.get("expirationTime", 0) < time.time():
        pool = md("DAILY_CHALLENGE_DATA")
        picks = random.sample(pool, min(3, len(pool)))
        dc = {"dailyChallenges": [{"dailyChallengeLogical": p["Logical"], "progress": 0,
                                   "completionGoal": rand_range(p.get("TaskNumber"), 1)} for p in picks],
              "state": "IN_PROGRESS", "expirationTime": time.time() + 86400, "numberOfResets": 0}
        s["DailyChallenges"] = dc
    return dc


def progress(s, action, subtype=None, amount=1, value=None):
    """Advances daily challenges by ActionType (DAILY_CHALLENGE_DATA); value sets instead of adds."""
    defs = md_by_logical("DAILY_CHALLENGE_DATA")
    for c in daily(s)["dailyChallenges"]:
        d = defs.get(c["dailyChallengeLogical"], {})
        if d.get("ActionType") != action or (d.get("SubType") and d.get("SubType") != subtype):
            continue
        new = max(c["progress"], value) if value is not None else c["progress"] + amount
        c["progress"] = min(c["completionGoal"], new)


def add_currency(s, cur, amount):
    if not amount:
        return
    s["Currency"][cur] = max(0, s["Currency"].get(cur, 0) + amount)
    if cur == "PARTS" and amount > 0:
        progress(s, "CollectParts", amount=amount)


def spend(s, cur, amount):
    """Takes currency if the player has enough; returns False otherwise."""
    if s["Currency"].get(cur, 0) < amount:
        return False
    s["Currency"][cur] -= amount
    return True


def streak_win(s):
    st = s["StreakData"]
    st["CurrentStreak"] += 1
    st["BestStreak"] = max(st["BestStreak"], st["CurrentStreak"])


# ---------------------------------------------------------------- CloudScript functions

def cs_auth(s, p, fn):
    sd = template(fn)
    if isinstance(sd.get("VersionMemento"), dict):
        sd["VersionMemento"]["MasterDataVersion"] = md_version()
    sd["currentSessionToken"] = s["SessionToken"]
    if fn == "AuthenticationResponse":
        sd["PlayerProfile"] = profile(s)
        sd["PlayerTitleId"] = s["TitlePlayerId"]
    return sd


def cs_get_player_data(s, p):
    sd = template("GET_PLAYER_DATA")
    sd.update({k: s[k] for k in ("StreakData", "Currency", "Inventory", "CPUInventory", "ModInventory",
                                 "PlayerDeviceData", "Inbox", "PlayerTutorialData", "PlayerFeatureFlags",
                                 "PlayerStatsData", "PlayerAlertData", "friendCode",
                                 "UnlockedEndoskeletonSlots", "PurchasedEndoskeletonSlots")})
    sd["PlayerProfile"] = profile(s)
    sd["PlayerTitleId"] = s["TitlePlayerId"]
    sd["Time"] = round(time.time(), 2)
    return sd


def cs_get_owned_goods(s, p):
    return {"Goods": s["Goods"], "UnlockedEndoskeletonSlots": s["UnlockedEndoskeletonSlots"],
            "PurchasedEndoskeletonSlots": s["PurchasedEndoskeletonSlots"], "StreakData": s["StreakData"],
            "Currency": s["Currency"], "Inventory": s["Inventory"], "PlayerDeviceData": s["PlayerDeviceData"]}


def cs_save_tutorial_step(s, p):
    # A step with a guide node sets that tutorial's position; an empty node clears it.
    entries = s["PlayerTutorialData"]["Entries"]
    for step in p.get("steps") or []:
        base = step.get("BaseData") or {}
        key, node = base.get("tutorialKey"), base.get("guideNodeId")
        entries[:] = [e for e in entries if e.get("TutorialKey") != key]
        if node:
            entries.insert(0, {"GuideNodeId": node, "TutorialKey": key})
    return {"PlayerTutorialData": s["PlayerTutorialData"], "PlayerFeatureFlags": s["PlayerFeatureFlags"]}


FLAG_MAP = {"allowAlerts": "AlertState", "allowSpawns": "SpawnState", "allowEssence": "EssenceState",
            "allowScaryMood": "ScaryMoodState", "allowTopBar": "TopBarState", "allowStaySafe": "StaySafeState",
            "allowResultsReturnToCamera": "ResultsReturnToCameraState", "allowScreenSleep": "ScreenSleepState"}


def cs_set_feature_flags(s, p):
    # allowX = 1 -> state 0 (allowed), allowX = 0 -> state 2 (blocked)
    entry = p.get("entryObject") or {}
    key = entry.get("tutorialKey")
    flags = s["PlayerFeatureFlags"].setdefault("flags", [])
    target = next((f for f in flags if f.get("TutorialKey") == key), None)
    if target is None:
        target = {"SkipTosState": 0, "TutorialKey": key}
        flags.append(target)
    for req_key, state_key in FLAG_MAP.items():
        if req_key in entry:
            target[state_key] = 0 if entry[req_key] else 2
    return {"PlayerFeatureFlags": s["PlayerFeatureFlags"]}


def cs_send_inbox_alert(s, p):
    add_inbox(s, p.get("alertId"))
    return {"PlayerProfile": profile(s), "PlayerTitleId": s["TitlePlayerId"], "Inbox": s["Inbox"]}


def add_inbox(s, logical, tokens=None):
    """Adds an ALERT_DATA message to the inbox (once per non-repeatable alert)."""
    alert = md_by_logical("ALERT_DATA").get(logical)
    repeatable = (alert or {}).get("Repeatable") == "Yes"
    if alert and (repeatable or not any(m.get("Logical") == alert["Logical"] for m in s["Inbox"].values())):
        body = alert.get("EventBody") or {}
        mid = str(uuid.uuid4())
        s["Inbox"][mid] = {
            "TemplateBundle": body.get("TemplateBundle", ""), "TemplatePrefab": body.get("TemplatePrefab", ""),
            "audio": "", "body": body.get("DisplayTextBody", ""), "date": now_ms(),
            "from": body.get("DisplayTextFrom", ""), "icon": "", "id": mid,
            "image": body.get("MessageImage", ""), "Logical": alert["Logical"], "read": False,
            "rewards": {"AnimatronicRewards": {}, "CPURewards": {}, "CurrencyRewards": {}, "ModRewards": {}},
            "subject": body.get("DisplayTextSubject", ""), "to": body.get("DisplayTextTo", ""),
            # Inbox_01 is the "unread" folder; it is dropped when the message is read.
            "tags": ["Inbox_00", "Inbox_01", alert.get("InboxFolderDestination", "Inbox_04")],
            "tokens": tokens or {"players_name": s["PlayFabId"]},
            "trigger": {"triggerDelayMaxSec": 0, "triggerDelayMinSec": 0, "triggerLogical": ""},
        }


def cs_batch_inbox_update(s, p):
    for mid in p.get("messagesToMarkRead") or []:
        m = s["Inbox"].get(mid)
        if m:
            m["read"] = True
            m["tags"] = [t for t in m["tags"] if t != "Inbox_01"]
    for mid in p.get("messagesToDelete") or []:
        s["Inbox"].pop(mid, None)
    return {"Inbox": s["Inbox"]}


def cs_get_animatronic_data_by_id(s, p):
    e = make_entity(s, p.get("cpuId"), origin=5, plush=p.get("plushSuitId"))
    return {"TransientAnimatronicEntity": e, "CpuId": p.get("cpuId"), "PlushSuitId": p.get("plushSuitId")}


def cs_award_unique_rewards(s, p):
    # First tutorial encounter: the CPU's parts reward plus a one-time Faz-Coin gift.
    cpu = md_by_logical("CPU_DATA").get(p.get("cpuId"), {})
    rewards = (cpu.get("Rewards") or {}).get("WanderingAnimatronics") or {}
    add_currency(s, "PARTS", rand_range(rewards.get("Parts"), 0))
    if not s["FtueRewarded"]:
        add_currency(s, "FAZ_TOKENS", FTUE_FAZ_TOKENS)
        s["FtueRewarded"] = True
    streak_win(s)
    return {"StreakData": s["StreakData"]}


def own_entity_slot(s, entity_id):
    for slot in s["Warehouse"]:
        if entity_id and slot.get("entityId") == entity_id:
            return slot
    return None


def free_slot(slot, wear_loss=0):
    slot.update({"status": "Available", "entityId": "", "receiverId": "", "appointmentId": "",
                 "lastCommand": round(time.time(), 3)})
    slot["wearAndTear"] = max(0, slot.get("wearAndTear", 100) - wear_loss)


def deliver_incoming(s):
    """Animatronics sent to yourself (or lured) arrive after a short trip."""
    arrived = {}
    now = time.time()
    for item in list(s["Incoming"]):
        if item["at"] <= now:
            e = item["entity"]
            s["Entities"][e["entityId"]] = e
            arrived[e["entityId"]] = e
            s["Incoming"].remove(item)
            slot = own_entity_slot(s, e["entityId"])
            if slot:
                slot["status"] = "Attacking"
    return arrived


def cs_request_entities(s, p):
    new = deliver_incoming(s)
    if spawns_allowed(s) and wild_count(s) < MAX_WILD and random.random() < SPAWN_CHANCE:
        cands = spawn_candidates(s)
        if cands:
            e = make_entity(s, random.choice(cands), origin=0)
            s["Entities"][e["entityId"]] = e
            new[e["entityId"]] = e
    if not new:
        return {}
    return {"StreakData": s["StreakData"], "NewAnimatronicEntities": new}


def cs_save_entities(s, p):
    for eid, data in (p.get("entityData") or {}).items():
        if eid in s["Entities"]:
            deep_merge(s["Entities"][eid], data)
    return {}


def cs_get_entity_data(s, p):
    return {"AnimatronicEntities": s["Entities"]}


def cs_remove_entity(s, p):
    s["Entities"].pop(p.get("EntityId") or p.get("entityId"), None)
    return {}


def finish_encounter(s, e):
    """Bookkeeping shared by winning and losing: frees your own endo, counts Shadow Bonnie."""
    origin = (e.get("originData") or {}).get("animatronicOrigin")
    slot = own_entity_slot(s, e.get("entityId"))
    if slot:
        free_slot(slot, wear_loss=random.randint(1, 10))
    if origin == 2:
        cfg = e.get("animatronicConfigId", "")
        defeats = s["PlayerStatsData"]["plushSuitDefeatDataList"].setdefault("ShadowBonnie", {})
        if cfg in defeats:
            defeats[cfg] += 1


def cs_award_entity_rewards(s, p):
    sd = {}
    e = s["Entities"].pop(p.get("entityId"), None)
    if e:
        rewards = copy.deepcopy(e.get("rewardsV3") or {})
        parts = (rewards.get("CurrencyRewards") or {}).get("PARTS")
        if parts and active_charges(s, "SalvageScanner") and use_charge(s, "SalvageScanner"):
            bonus = ((device_def("SalvageScanner").get("Effects") or {}).get("SalvageScanner") or {}).get("PartsBonus", 1.25)
            rewards["CurrencyRewards"]["PARTS"] = int(round(parts * bonus))
            sd["PlayerDeviceData"] = s["PlayerDeviceData"]
        sd.update(apply_rewards(s, rewards))
        progress(s, "DefeatAnimatronic", subtype=base_animatronic(e.get("animatronicConfigId", "")))
        finish_encounter(s, e)
    streak_win(s)
    progress(s, "CurrentStreakLength", value=s["StreakData"]["CurrentStreak"])
    sd.update({"StreakData": s["StreakData"], "PlayerDailyChallengeData": daily(s), "Currency": s["Currency"]})
    if any(k in sd for k in ("Inventory", "CPUInventory", "ModInventory")):
        sd["WarehouseDataV2"] = s["Warehouse"]
    return sd


def cs_attack_lost(s, p):
    e = s["Entities"].pop(p.get("entityId"), None)
    if e:
        # The animatronic takes some of your remnant with it.
        add_currency(s, "ESSENCE", -((e.get("rewardsV3") or {}).get("EssenceOnLose") or 0))
        finish_encounter(s, e)
    s["StreakData"]["CurrentStreak"] = 0
    return {"StreakData": s["StreakData"], "Currency": s["Currency"]}


def cs_rollover(s, p):
    return {"StreakData": s["StreakData"], "PlayerDailyChallengeData": daily(s)}


def cs_warehouse(s, p):
    return {"WarehouseDataV2": s["Warehouse"]}


# ---------------------------------------------------------------- workshop

def slot_at(s, p, key="slotId"):
    i = int(p.get(key, p.get("slot", 0)) or 0)
    while len(s["Warehouse"]) <= i:
        s["Warehouse"].append(new_slot())
    return s["Warehouse"][i]


def new_slot():
    return {"status": "Available", "lastCommand": 0, "entityId": "", "wearAndTear": 100,
            "endoskeleton": {"cpu": "BareEndo", "plushSuit": "BareEndo", "mods": [], "essence": 0},
            "receiverId": "", "appointmentId": ""}


REMNANT_PER_ESSENCE_LEVEL = 1


def cs_set_endoskeleton(s, p):
    slot = slot_at(s, p, "slot")
    config = p.get("config") or {}
    old = slot["endoskeleton"].get("essence", 0) or 0
    new = config.get("essence", old) or 0
    if new > old:
        # Infusing remnant into an endo costs remnant from your balance.
        add_currency(s, "ESSENCE", -REMNANT_PER_ESSENCE_LEVEL * (new - old))
    slot["endoskeleton"] = {"cpu": config.get("cpu", "BareEndo"), "plushSuit": config.get("plushSuit", "BareEndo"),
                            "mods": list(config.get("mods") or []), "essence": new}
    return {"Currency": s["Currency"], "WarehouseDataV2": s["Warehouse"]}


def cs_repair(s, p):
    slot = slot_at(s, p)
    add_currency(s, "PARTS", -int(p.get("cost") or 0))
    slot["wearAndTear"] = 100
    return {"WarehouseDataV2": s["Warehouse"], "Currency": s["Currency"]}


def cs_sell_mods(s, p):
    mods = md_by_logical_key("MODS_DATA", "ModLogical")
    for mod, n in (p.get("mods") or {}).items():
        n = min(int(n), s["ModInventory"].get(mod, 0))
        s["ModInventory"][mod] = s["ModInventory"].get(mod, 0) - n
        add_currency(s, "PARTS", n * int((mods.get(mod) or {}).get("PartsBuyback") or 0))
    return {"ModInventory": s["ModInventory"], "Currency": s["Currency"]}


def md_by_logical_key(name, key):
    return {e[key]: e for e in md(name) if key in e}


# ---------------------------------------------------------------- scavenging

def cs_start_scavenge(s, p):
    slot = slot_at(s, p)
    endo = slot["endoskeleton"]
    e = make_entity(s, endo["cpu"], origin=3, plush=endo["plushSuit"])
    e["endoskeleton"] = copy.deepcopy(endo)
    e["stateData"]["animatronicState"] = 15
    e["moveStateData"].update({"maxNodes": 2, "nodeTravelTime": 20})
    e["rewardsV3"]["CurrencyRewards"] = {}
    s["Entities"][e["entityId"]] = e
    slot.update({"status": "ScavengeAppointment", "lastCommand": round(time.time(), 3),
                 "entityId": e["entityId"], "appointmentId": p.get("appointmentId", "")})
    return {"WarehouseDataV2": s["Warehouse"], "NewAnimatronicEntities": {e["entityId"]: e}}


def scavenge_rewards(appointment_id):
    a = md_by_logical("SCAVENGE_APPOINTMENT_DATA").get(appointment_id) or \
        md("CONFIG_DATA")[0].get("Scavenging") or {}
    r = {"ModRewards": {}, "AnimatronicRewards": {}, "CurrencyRewards": {}, "CPURewards": {}}
    parts = rand_range(a.get("Parts"), 0)
    if parts:
        r["CurrencyRewards"]["PARTS"] = parts
    if random.random() < (a.get("CommonRewardChance") or 0):
        mod = pick_mod(2)
        if mod:
            r["ModRewards"][mod] = 1
    if random.random() < (a.get("RareRewardChance") or 0):
        mod = pick_mod(10)
        if mod:
            r["ModRewards"][mod] = r["ModRewards"].get(mod, 0) + 1
    if random.random() < (a.get("PlushSuitChance") or 0):
        suits = [x["Logical"] for x in md("PLUSHSUIT_DATA") if x.get("PlayerAcquirable")]
        if suits:
            r["AnimatronicRewards"][random.choice(suits)] = {"PlushSuit": 1}
    wear = rand_range(a.get("WearAndTearDamage"), 0) if random.random() < (a.get("WearAndTearChance") or 0) else 0
    return r, wear


def cs_collect_scavenge(s, p):
    slot = slot_at(s, p)
    rewards, wear = scavenge_rewards(slot.get("appointmentId"))
    eid = slot.get("entityId", "")
    s["Entities"].pop(eid, None)
    free_slot(slot, wear_loss=wear)
    sd = apply_rewards(s, rewards)
    sd.update({"ScavengeRecall": [eid], "WarehouseDataV2": s["Warehouse"], "RewardsV2": rewards,
               "ModInventory": s["ModInventory"]})
    return sd


def cs_recall_slot(s, p):
    """Recall a scavenging endo, or one you sent to attack, back to the workshop."""
    slot = slot_at(s, p)
    eid = slot.get("entityId", "")
    s["Entities"].pop(eid, None)
    s["Incoming"] = [i for i in s["Incoming"] if i["entity"]["entityId"] != eid]
    free_slot(slot)
    return {"WarehouseDataV2": s["Warehouse"], "ScavengeRecall": [eid]}


def cs_send_scavenge(s, p):
    """Older free-roam scavenging: behaves like a default appointment."""
    p = dict(p)
    p.setdefault("appointmentId", "Scavenge30")
    sd = cs_start_scavenge(s, p)
    slot_at(s, p)["status"] = "Scavenging"
    return sd


# ---------------------------------------------------------------- sending animatronics

SEND_TRAVEL_SECONDS = 20


def cs_send_attack(s, p):
    """Send an endo to attack a player. Offline the only player is you, so it comes back
    to you as an attacker after a short trip (as in the ARchive's "send to yourself")."""
    slot = slot_at(s, p)
    endo = slot["endoskeleton"]
    e = make_entity(s, endo["cpu"], origin=4, plush=endo["plushSuit"], wear=slot.get("wearAndTear", 100))
    e["endoskeleton"] = copy.deepcopy(endo)
    e["rewardsV3"]["AnimatronicRewards"], e["rewardsV3"]["CPURewards"], e["rewardsV3"]["ModRewards"] = {}, {}, {}
    slot.update({"status": "Sent", "lastCommand": round(time.time(), 3), "entityId": e["entityId"],
                 "receiverId": p.get("userId") or s["PlayFabId"], "appointmentId": ""})
    s["Incoming"].append({"at": time.time() + SEND_TRAVEL_SECONDS, "entity": e})
    progress(s, "SendAnimatronic")
    return {"WarehouseDataV2": s["Warehouse"]}


def cs_express_delivery(s, p):
    """Pay Faz-Coins to bring an animatronic on the map to you now. The client only sends the
    request; it picks up the change from UpdateAnimatronicEntities in the response."""
    cost = int((md("CONFIG_DATA")[0].get("ExpressDelivery") or {}).get("CostFazCoins") or 50)
    eid = p.get("entityId")
    entity = s["Entities"].get(eid)
    incoming = next((i for i in s["Incoming"] if i["entity"]["entityId"] == eid), None)
    if incoming:
        entity = incoming["entity"]
    if entity is None or not spend(s, "FAZ_TOKENS", cost):
        return {"Currency": s["Currency"]}
    entity["stateData"]["expressDelivery"] = True
    if incoming:
        incoming["at"] = 0
    return {"Currency": s["Currency"], "UpdateAnimatronicEntities": {eid: entity}}


# ---------------------------------------------------------------- Shadow Bonnie / remnant

ESSENCE_TIERS = ["ShadowBonnie_Easy", "ShadowBonnie_Medium", "ShadowBonnie_Hard", "ShadowBonnie_Insane"]


def cs_start_essence_encounter(s, p):
    defeats = s["PlayerStatsData"]["plushSuitDefeatDataList"].setdefault("ShadowBonnie", {})
    tier = next((t for t in ESSENCE_TIERS if not defeats.get(t)), ESSENCE_TIERS[-1])
    e = make_entity(s, tier, origin=2, plush="ShadowBonnie")
    s["Entities"][e["entityId"]] = e
    return {"NewAnimatronicEntities": {e["entityId"]: e}}


ESSENCE_STATE = {"Counts": {}, "LastCategoryTriggers": {}, "LastGlobalTrigger": 0, "LastThreatTrigger": 0,
                 "Nodes": {}}


def essence_types():
    return {t["NodeType"]["Logical"]: t for t in md("ESSENCE_TYPES_DATA")}


def cs_spawn_motes(s, p):
    """Remnant nodes the game asked for (objectTypes): roll a node colour by SelectionWeight,
    "NoMote" means nothing spawns. Mote ids are remembered so collecting knows the colour."""
    types = essence_types()
    emf = active_charges(s, "EMFMeter") > 0
    bonus = ((device_def("EMFMeter").get("Effects") or {}).get("EMFMeter") or {}).get("RarityBonus", 1)
    weights = []
    for x in types.values():
        w = x["NodeType"]["SelectionWeight"]
        # An active EMF meter makes the rarer colours (worth more than 1 remnant) likelier.
        per = ((x.get("MoteOverrides") or {}).get("SpawnBehavior") or {}).get("EssencePerMote") or 0
        weights.append(w * (1 + bonus) if emf and per > 1 else w)
    nodes = []
    for category in p.get("objectTypes") or []:
        t = random.choices(list(types.values()), weights=weights)[0]
        if not t["NodeType"].get("HasMote"):
            continue
        colour = t["NodeType"]["Logical"]
        count = (t.get("MoteOverrides") or {}).get("SpawnBehavior", {}).get("StartingMotesPerNode", 1)
        motes = [str(uuid.uuid4()) for _ in range(count)]
        for m in motes:
            s.setdefault("Motes", {})[m] = colour
        nodes.append({"category": category, "id": colour + str(uuid.uuid4()), "motes": motes,
                      "spawnTime": round(time.time(), 3), "type": colour})
    # Keep the remembered motes bounded.
    if len(s.get("Motes", {})) > 200:
        s["Motes"] = dict(list(s["Motes"].items())[-200:])
    if not nodes:
        return {}
    sd = {"EssencesToSpawn": nodes, "PlayerEssenceData": ESSENCE_STATE}
    if emf:
        use_charge(s, "EMFMeter")
        sd["PlayerDeviceData"] = s["PlayerDeviceData"]
    return sd


def mote_value(s, mote_id):
    """(colour, remnant) of a collected mote; unknown ids get a weighted random colour."""
    types = essence_types()
    colour = s.get("Motes", {}).pop(mote_id, None)
    if colour not in types:
        has = [t for t in types.values() if t["NodeType"].get("HasMote")]
        colour = random.choices(has, weights=[x["NodeType"]["SelectionWeight"] for x in has])[0]["NodeType"]["Logical"]
    return colour, types[colour]["MoteOverrides"]["SpawnBehavior"]["EssencePerMote"]


def cs_collect_motes(s, p):
    for mote_id in p.get("motesCollectedList") or []:
        colour, amount = mote_value(s, mote_id)
        add_currency(s, "ESSENCE", amount)
        s["PlayerStatsData"]["totalEssence"] += amount
        progress(s, "CollectRemnant", subtype=colour)   # generic challenges match any colour
    return {"PlayerStatsData": s["PlayerStatsData"], "Currency": s["Currency"],
            "PlayerDailyChallengeData": daily(s)}


def cs_essence_level_up(s, p):
    """Sends the remnant milestone message (REMNANT_DEBUFF_DATA) once per milestone."""
    total = s["PlayerStatsData"]["totalEssence"]
    tiers = [t["RemnantDebuff"] for t in md("REMNANT_DEBUFF_DATA")]
    reached = [t for t in tiers if t.get("RemnantCollected", 0) <= total]
    nxt = next((t for t in tiers if t.get("RemnantCollected", 0) > total), None)
    level = len(reached) - 1
    if level > s.get("RemnantMilestone", 0):
        s["RemnantMilestone"] = level
        cur = reached[-1]
        add_inbox(s, "Remnant-Debuff", tokens={
            "percent_increase": "%d%%" % round((cur.get("ShockWindowIncrease", 1) - 1) * 100),
            "next_milestone_amount": str(nxt["RemnantCollected"]) if nxt else ""})
    return {"Inbox": s["Inbox"]}


# ---------------------------------------------------------------- devices and store

def device_def(name):
    return md_by_logical_key("DEVICES_DATA", "DeviceLogical").get(name, {})


def cs_activate_device(s, p):
    name = p.get("deviceConfigId")
    dev = s["PlayerDeviceData"]
    if name:
        # The client only offers devices you own; trust it even if our count drifted.
        dev["purchased"][name] = max(0, dev["purchased"].get(name, 0) - 1)
        d = device_def(name)
        exp = d.get("Expiration") or {}
        effects = d.get("Effects") or {}
        if effects.get("Type") == "Lure":
            lured = (effects.get("Lure") or {}).get("AnimatronicLured") or "FreddyFazbear"
            cpu = lured if lured in md_by_logical("CPU_DATA") else "FreddyFazbear"
            e = make_entity(s, cpu, origin=1, plush=lured)
            s["Incoming"].append({"at": time.time() + rand_range(effects.get("Lure"), 10), "entity": e})
        elif exp:
            did = str(now_ms())
            state = {"expirationTimeStamp": None, "expirationType": "Charges", "scalar": exp.get("Count", 1)}
            if "Seconds" in exp:
                state = {"expirationTimeStamp": int(time.time() + exp["Seconds"]), "expirationType": "Time",
                         "scalar": 1}
            dev["active"].setdefault(name, {})[did] = {"deviceConfigId": name, "deviceId": did,
                                                        "deviceState": state, "deviceType": name}
    return {"PlayerDeviceData": dev}


def active_charges(s, name):
    """Remaining charges of an active device (0 if none)."""
    return sum(int(d["deviceState"].get("scalar") or 0)
               for d in s["PlayerDeviceData"]["active"].get(name, {}).values()
               if d["deviceState"].get("expirationType") == "Charges")


def use_charge(s, name):
    """Consumes one charge of an active device; removes it when empty."""
    for did, d in list(s["PlayerDeviceData"]["active"].get(name, {}).items()):
        st = d["deviceState"]
        if st.get("expirationType") == "Charges" and (st.get("scalar") or 0) > 0:
            st["scalar"] -= 1
            if st["scalar"] <= 0:
                del s["PlayerDeviceData"]["active"][name][did]
            return True
    return False


def expire_timed_devices(s):
    now = time.time()
    for devices in s["PlayerDeviceData"]["active"].values():
        for did, d in list(devices.items()):
            ts = d["deviceState"].get("expirationTimeStamp")
            if d["deviceState"].get("expirationType") == "Time" and ts and ts < now:
                del devices[did]


def cs_expire_device(s, p):
    did = str(p.get("activeDeviceId"))
    for devices in s["PlayerDeviceData"]["active"].values():
        devices.pop(did, None)
    return {"PlayerDeviceData": s["PlayerDeviceData"]}


def store_prices():
    prices = {}
    for store in (template("GET_STORE_ITEMS_V2").get("StoreItems") or {}).get("Stores", []):
        for item in store.get("Items", []):
            prices[item["ItemId"]] = item.get("VirtualCurrencyPrices") or {}
    return prices


CURRENCY_CODES = {"FC": "FAZ_TOKENS", "PA": "PARTS", "RE": "ESSENCE"}


def purchase(s, req):
    """PlayFab Client/PurchaseItem: prices come from the store list, contents from STORE_DATA."""
    item_id, code = req.get("ItemId"), req.get("VirtualCurrency")
    product = md_by_logical_key("STORE_DATA", "PurchasableLogical").get(item_id)
    price = store_prices().get(item_id, {}).get(code)
    if price is None and product:
        cost = product.get("Cost") or {}
        price = cost.get("HardCurrency") if code == "FC" else cost.get("SoftCurrency")
    if not product or price is None or code not in CURRENCY_CODES:
        return error(400, "ItemNotFound", 1047, "Item %s is not for sale for %s" % (item_id, code))
    if product.get("Repeatable") == "No" and any(g.get("ItemId") == item_id for g in s["Goods"]):
        return error(400, "ItemNotFound", 1047, "Item %s was already purchased" % item_id)
    if not spend(s, CURRENCY_CODES[code], int(price)):
        return error(400, "InsufficientFunds", 1059, "Insufficient funds")
    parent = add_good(s, item_id, "Bundle")
    parent.update({"UnitCurrency": code, "UnitPrice": int(price)})
    contents = list((product.get("Contents") or {}).values())
    bundle = []
    for c in contents:
        prefix = {"Device": "Device_", "PlushSuit": "PlushSuit_", "Mod": "Mod_"}.get(c.get("Type"), "")
        bundle += [prefix + c.get("Logical", "")] * (int(c.get("Qty") or 1) if c.get("Type") == "Device" else 1)
    items = [dict(parent, RemainingUses=1, UsesIncrementedBy=1, BundleContents=bundle)]
    for content in contents:
        kind, logical, qty = content.get("Type"), content.get("Logical"), int(content.get("Qty") or 1)
        if kind == "Device":
            give_device(s, logical, qty)
        elif kind == "PlushSuit":
            give_suit(s, logical)
        elif kind == "FazCoins":
            add_currency(s, "FAZ_TOKENS", qty)
        elif kind == "EndoskeletonSlot":
            s["PurchasedEndoskeletonSlots"] = s.get("PurchasedEndoskeletonSlots", 0) + 1
            s["Warehouse"].append(new_slot())
        elif kind == "CPU":
            give_cpu(s, logical, qty)
        elif kind == "Mod":
            give_mod(s, logical, qty)
    return ok({"Items": items})


# ---------------------------------------------------------------- daily challenges and rewards

DAILY_CHANGE_COST = 10


def cs_change_daily(s, p):
    dc = daily(s)
    current = {c["dailyChallengeLogical"] for c in dc["dailyChallenges"]}
    pool = [d for d in md("DAILY_CHALLENGE_DATA") if d["Logical"] not in current]
    if pool and (p.get("adWatched") or spend(s, "FAZ_TOKENS", DAILY_CHANGE_COST)):
        pick = random.choice(pool)
        for i, c in enumerate(dc["dailyChallenges"]):
            if c["dailyChallengeLogical"] == p.get("dailyChallengeToChangeLogical"):
                dc["dailyChallenges"][i] = {"dailyChallengeLogical": pick["Logical"], "progress": 0,
                                            "completionGoal": rand_range(pick.get("TaskNumber"), 1)}
        dc["numberOfResets"] = dc.get("numberOfResets", 0) + 1
    return {"Currency": s["Currency"], "StreakData": s["StreakData"], "PlayerDailyChallengeData": dc}


def give_reward_item(s, item):
    kind, sub, qty = item.get("RewardType"), item.get("RewardSubtype"), int(item.get("Quantity") or 1)
    if kind == "Currency":
        add_currency(s, {"FazCoins": "FAZ_TOKENS", "Parts": "PARTS", "Remnant": "ESSENCE"}.get(sub, "FAZ_TOKENS"), qty)
    elif kind == "Device":
        give_device(s, sub, qty)
    elif kind == "PlushSuit":
        give_suit(s, sub)
    elif kind == "CPU":
        give_cpu(s, sub, qty)
    elif kind == "Mod":
        give_mod(s, sub, qty)


def cs_collect_daily_rewards(s, p):
    dc = daily(s)
    sd = {"PlayerDailyChallengeData": dc}
    done = all(c["progress"] >= c["completionGoal"] for c in dc["dailyChallenges"])
    if done and dc.get("state") != "COLLECTED":
        pool = md("DAILY_CHALLENGE_REWARDS_DATA")
        reward = random.choices(pool, weights=[r.get("Weight") or 1 for r in pool])[0]
        for key in ("Item1", "Item2", "Item3"):
            if reward.get(key):
                give_reward_item(s, reward[key])
        dc["state"] = "COLLECTED"
        sd.update({"DailyChallengeRewardsLogical": reward["Logical"], "Currency": s["Currency"],
                   "PlayerDeviceData": s["PlayerDeviceData"], "CPUInventory": s["CPUInventory"],
                   "Inventory": s["Inventory"], "ModInventory": s["ModInventory"]})
    return sd


def cs_sequential_reward(s, p):
    logical = p.get("logical") or p.get("rewardLogical") or p.get("Logical")
    r = md_by_logical("SEQUENTIAL_REWARDS_DATA").get(logical)
    if r and logical not in s.setdefault("SequentialRewards", []):
        s["SequentialRewards"].append(logical)
        give_reward_item(s, r)
    return {"Currency": s["Currency"], "PlayerDeviceData": s["PlayerDeviceData"], "Inventory": s["Inventory"]}


# ---------------------------------------------------------------- profile and friends

def cs_save_avatar(s, p):
    s["AvatarId"] = p.get("avatarId") or "default"
    return {"PlayerProfile": profile(s), "PlayerTitleId": s["TitlePlayerId"]}


def cs_new_friend_code(s, p):
    s["friendCode"] = uuid.uuid4().hex[:10].upper()
    return {"friendCode": s["friendCode"]}


def cs_lookup_friend_code(s, p):
    # Offline there is nobody else to befriend.
    code = (p.get("friendCode") or "").upper()
    return {"lookupFriendCodeResponse": "userTriedToFriendSelf" if code == s["friendCode"] else "groupNotFound"}


def cs_configs(s, p):
    sd = template("GET_ALL_CONFIGS_V7")
    sd["MasterDataVersion"] = md_version()
    return sd


def cs_template(fn):
    return lambda s, p: template(fn)


def cs_empty(s, p):
    return {}


CLOUDSCRIPT = {
    "DeviceAuthenticationRequest": lambda s, p: cs_auth(s, p, "DeviceAuthenticationRequest"),
    "AuthenticationResponse": lambda s, p: cs_auth(s, p, "AuthenticationResponse"),
    "AUTHENTICATE_GETSOCIAL": cs_template("AUTHENTICATE_GETSOCIAL"),
    "GET_ALL_CONFIGS_V7": cs_configs,
    "GET_STORE_ITEMS_V2": cs_template("GET_STORE_ITEMS_V2"),
    "GET_PLAYER_DATA": cs_get_player_data,
    "GET_OWNED_GOODS": cs_get_owned_goods,
    "GET_PLAYER_FRIENDS": lambda s, p: {"friendsList": {}},
    "GET_ENTITY_DATA_V3": cs_get_entity_data,
    "GET_WAREHOUSE_DATA_V2": cs_warehouse,
    "GET_CPU_INVENTORY": lambda s, p: {"CPUInventory": s["CPUInventory"]},
    "REQUEST_ROLLOVER_DATA": cs_rollover,
    "SAVE_TUTORIAL_STEP": cs_save_tutorial_step,
    "SET_FEATURE_FLAGS": cs_set_feature_flags,
    "SEND_INBOX_ALERT_MESSAGE": cs_send_inbox_alert,
    "BATCH_INBOX_UPDATE": cs_batch_inbox_update,
    "GET_ANIMATRONIC_DATA_BY_ID": cs_get_animatronic_data_by_id,
    "AWARD_UNIQUE_REWARDS": cs_award_unique_rewards,
    "REQUEST_ENTITIES_V8": cs_request_entities,
    "SAVE_ENTITIES_V3": cs_save_entities,
    "REMOVE_ENTITY_V3": cs_remove_entity,
    "AWARD_ENTITY_REWARDS_V2": cs_award_entity_rewards,
    "ATTACK_MODE_LOST_V2": cs_attack_lost,
    "SET_ENDOSKELETON_CONFIG_V2": cs_set_endoskeleton,
    "REPAIR_ANIMATRONIC": cs_repair,
    "SELL_MODS": cs_sell_mods,
    "START_SCAVENGE_APPOINTMENT": cs_start_scavenge,
    "COLLECT_SCAVENGE_APPOINTMENT": cs_collect_scavenge,
    "RECALL_SCAVENGE_APPOINTMENT": cs_recall_slot,
    "SCAVENGE_PERIOD_CHECK_V4": cs_warehouse,
    "SEND_ANIMATRONIC_SCAVENGE_V3": cs_send_scavenge,
    "SEND_ANIMATRONIC_ATTACK_V2": cs_send_attack,
    "RECALL_ATTACKING_ANIMATRONIC": cs_recall_slot,
    "EXPRESS_DELIVERY": cs_express_delivery,
    "START_ESSENCE_ENCOUNTER_V3": cs_start_essence_encounter,
    "ESSENCE_NODE_SPAWN_V2": cs_spawn_motes,
    "ESSENCE_NODE_COLLECT_V2": cs_collect_motes,
    "ESSENCE_LEVEL_UP": cs_essence_level_up,
    "ACTIVATE_DEVICE": cs_activate_device,
    "EXPIRE_DEVICE": cs_expire_device,
    "CHANGE_SINGLE_DAILY_CHALLENGE": cs_change_daily,
    "COLLECT_DAILY_CHALLENGE_REWARDS": cs_collect_daily_rewards,
    "GET_SEQUENTIAL_REWARD": cs_sequential_reward,
    "SAVE_AVATAR": cs_save_avatar,
    "GENERATE_NEW_FRIENDCODE": cs_new_friend_code,
    "LOOKUP_FRIENDCODE": cs_lookup_friend_code,
    "CLIENT_HEARTBEAT": cs_empty,
}


# ---------------------------------------------------------------- PlayFab calls

def ok(data):
    return 200, {"code": 200, "status": "OK", "data": data}


def error(code, name, error_code, message):
    # The SDK sends X-ReportErrorAsSuccess, so PlayFab errors arrive as HTTP 200.
    return 200, {"code": code, "status": "BadRequest", "error": name, "errorCode": error_code,
                 "errorMessage": message}


def login(s):
    s["SessionToken"] = str(uuid.uuid4())
    return ok({
        "SessionTicket": s["SessionTicket"], "PlayFabId": s["PlayFabId"], "NewlyCreated": False,
        "SettingsForUser": {"NeedsAttribution": False, "GatherDeviceInfo": False, "GatherFocusInfo": False},
        "LastLoginTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "EntityToken": {"EntityToken": s["SessionTicket"], "TokenExpiration": "2099-01-01T00:00:00Z",
                        "Entity": {"Id": s["TitlePlayerId"], "Type": "title_player_account",
                                   "TypeString": "title_player_account"}},
        "TreatmentAssignment": {"Variants": [], "Variables": []},
    })


def leaderboard(s, req):
    stat = s["StreakData"]["BestStreak"]
    name = s.get("DisplayName") or s["PlayFabId"]
    return ok({"Leaderboard": [{"PlayFabId": s["PlayFabId"], "DisplayName": name, "StatValue": stat,
                                "Position": 0, "Profile": {"PlayerId": s["PlayFabId"], "DisplayName": name,
                                                           "AvatarUrl": s.get("AvatarId", "default")}}],
               "Version": 0})


def handle(path, req):
    req = req if isinstance(req, dict) else {}
    with lock:
        s = load_state()
        s.setdefault("SessionToken", str(uuid.uuid4()))
        migrate(s)
        expire_timed_devices(s)
        if path.startswith("/Client/LoginWith"):
            result = login(s)
        elif path == "/Client/PurchaseItem":
            result = purchase(s, req)
        elif path == "/Client/UpdateUserTitleDisplayName":
            s["DisplayName"] = (req.get("DisplayName") or "").strip()[:25] or s.get("DisplayName")
            result = ok({"DisplayName": s.get("DisplayName")})
        elif path == "/Client/GetLeaderboard":
            result = leaderboard(s, req)
        elif path == "/Profile/SetProfileLanguage":
            result = ok({"VersionNumber": 1, "OperationResult": "Updated"})
        elif path == "/Client/ExecuteCloudScript":
            fn = req.get("FunctionName")
            impl = CLOUDSCRIPT.get(fn)
            if impl is None:
                return None
            params = req.get("FunctionParameter") or {}
            sd = {"ProfileRead": {}, "ProfileWrite": {}}
            sd.update(impl(s, params))
            # The real server echoes the parameters back next to scriptData.
            fr = {"playerPassThroughData": {}}
            fr.update(result_defaults(fn))
            fr.update(params)
            fr.update({"scriptData": sd, "scriptError": {}})
            result = ok({"FunctionName": fn, "Revision": 1, "FunctionResult": fr, "Logs": [],
                         "ExecutionTimeSeconds": 0.01, "ProcessorTimeSeconds": 0.001,
                         "MemoryConsumedBytes": 0, "APIRequestsIssued": 0, "HttpRequestsIssued": 0})
        else:
            return None
        save_state(s)
        return result
