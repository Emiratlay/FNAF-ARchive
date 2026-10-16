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
CUSTOM_SECTIONS = {"mods": "MODS_DATA", "plushsuits": "PLUSHSUIT_DATA", "cpus": "CPU_DATA", "loc": "LOC_DATA"}

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
    return {"avatarId": "default", "displayName": s["PlayFabId"], "fazPassInviteTokenList": [],
            "inviteTokenList": [], "userId": s["PlayFabId"], "userName": s["PlayFabId"]}


# ---------------------------------------------------------------- animatronics

def make_entity(s, cpu_id, origin, plush=None, wear=None):
    """origin: 0 = wild spawn, 3 = own endo sent scavenging, 5 = tutorial/transient."""
    cpu = md_by_logical("CPU_DATA").get(cpu_id, {})
    plush = plush or cpu.get("PlushSuitRef") or cpu_id.split("_")[0]
    rewards = (cpu.get("Rewards") or {}).get("WanderingAnimatronics") or {}
    nodes = cpu.get("MapNodes") or {}
    ts = now_ms()
    parts = rand_range(rewards.get("Parts"), 0)
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
        "rewardsV3": {"AnimatronicRewards": {}, "CPURewards": {},
                      "CurrencyRewards": {"PARTS": parts} if parts else {},
                      "EssenceOnLose": rand_range(rewards.get("EssenceOnLose"), 0) if origin == 0 else 0,
                      "ModRewards": {}},
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


def add_currency(s, cur, amount):
    if not amount:
        return
    s["Currency"][cur] = s["Currency"].get(cur, 0) + amount
    if cur == "PARTS":
        for c in daily(s)["dailyChallenges"]:
            if c["dailyChallengeLogical"] == "Collect_Parts":
                c["progress"] = min(c["completionGoal"], c["progress"] + amount)


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
    alert = md_by_logical("ALERT_DATA").get(p.get("alertId"))
    if alert and not any(m.get("Logical") == alert["Logical"] for m in s["Inbox"].values()):
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
            "tokens": {"players_name": s["PlayFabId"]},
            "trigger": {"triggerDelayMaxSec": 0, "triggerDelayMinSec": 0, "triggerLogical": ""},
        }
    return {"PlayerProfile": profile(s), "PlayerTitleId": s["TitlePlayerId"], "Inbox": s["Inbox"]}


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


def cs_request_entities(s, p):
    sd = {}
    if spawns_allowed(s) and wild_count(s) < MAX_WILD and random.random() < SPAWN_CHANCE:
        cands = spawn_candidates(s)
        if cands:
            e = make_entity(s, random.choice(cands), origin=0)
            s["Entities"][e["entityId"]] = e
            sd = {"StreakData": s["StreakData"], "NewAnimatronicEntities": {e["entityId"]: e}}
    return sd


def cs_save_entities(s, p):
    for eid, data in (p.get("entityData") or {}).items():
        if eid in s["Entities"]:
            deep_merge(s["Entities"][eid], data)
    return {}


def cs_get_entity_data(s, p):
    return {"AnimatronicEntities": s["Entities"]}


def cs_award_entity_rewards(s, p):
    e = s["Entities"].pop(p.get("entityId"), None)
    if e:
        for cur, amount in ((e.get("rewardsV3") or {}).get("CurrencyRewards") or {}).items():
            add_currency(s, cur, amount)
    streak_win(s)
    return {"StreakData": s["StreakData"], "PlayerDailyChallengeData": daily(s), "Currency": s["Currency"]}


def cs_attack_lost(s, p):
    s["Entities"].pop(p.get("entityId"), None)
    s["StreakData"]["CurrentStreak"] = 0
    return {"StreakData": s["StreakData"]}


def cs_rollover(s, p):
    return {"StreakData": s["StreakData"], "PlayerDailyChallengeData": daily(s)}


def cs_warehouse(s, p):
    return {"WarehouseDataV2": s["Warehouse"]}


def cs_start_scavenge(s, p):
    slot = s["Warehouse"][int(p.get("slotId", 0))]
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
    "REQUEST_ROLLOVER_DATA": cs_rollover,
    "SAVE_TUTORIAL_STEP": cs_save_tutorial_step,
    "SET_FEATURE_FLAGS": cs_set_feature_flags,
    "SEND_INBOX_ALERT_MESSAGE": cs_send_inbox_alert,
    "BATCH_INBOX_UPDATE": cs_batch_inbox_update,
    "GET_ANIMATRONIC_DATA_BY_ID": cs_get_animatronic_data_by_id,
    "AWARD_UNIQUE_REWARDS": cs_award_unique_rewards,
    "REQUEST_ENTITIES_V8": cs_request_entities,
    "SAVE_ENTITIES_V3": cs_save_entities,
    "AWARD_ENTITY_REWARDS_V2": cs_award_entity_rewards,
    "ATTACK_MODE_LOST_V2": cs_attack_lost,
    "START_SCAVENGE_APPOINTMENT": cs_start_scavenge,
    "CLIENT_HEARTBEAT": cs_empty,
    "ESSENCE_NODE_SPAWN_V2": cs_empty,
}


# ---------------------------------------------------------------- PlayFab calls

def ok(data):
    return 200, {"code": 200, "status": "OK", "data": data}


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
    return ok({"Leaderboard": [{"PlayFabId": s["PlayFabId"], "DisplayName": s["PlayFabId"], "StatValue": stat,
                                "Position": 0, "Profile": {"PlayerId": s["PlayFabId"],
                                                           "DisplayName": s["PlayFabId"], "AvatarUrl": "default"}}],
               "Version": 0})


def handle(path, req):
    req = req if isinstance(req, dict) else {}
    with lock:
        s = load_state()
        s.setdefault("SessionToken", str(uuid.uuid4()))
        if path.startswith("/Client/LoginWith"):
            result = login(s)
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
