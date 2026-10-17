"""
Replays every recorded request (captures/*.json) through game.py in time order and checks that
each response has every key the real server returned (random/dynamic values excluded).

Usage:  python test_kayitlar.py [path to captures]
"""
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game  # noqa: E402

CAPTURES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
DYNAMIC = {"Inbox", "AnimatronicEntities", "NewAnimatronicEntities", "Inventory", "CPUInventory", "Currency",
           "entityData", "ProfileRead", "ProfileWrite", "dailyChallenges", "Entries", "flags",
           "plushSuitDefeatDataList", "Leaderboard", "Goods", "ModInventory", "purchased", "active", "RewardsV2",
           "friendsList"}
RANDOM_CALLS = {"REQUEST_ENTITIES_V8", "ESSENCE_NODE_SPAWN_V2", "AWARD_ENTITY_REWARDS_V2"}


def main():
    game.STATE_FILE = os.path.join(os.path.dirname(game.STATE_FILE), "_replay_test.json")
    if os.path.exists(game.STATE_FILE):
        os.remove(game.STATE_FILE)
    events = []
    for f in glob.glob(os.path.join(CAPTURES, "*.json")):
        for e in json.load(open(f, encoding="utf-8")):
            fp = (e["request"] or {}).get("FunctionParameter") or {}
            events.append((e["time"], fp.get("executeCloudScriptCount", -1), e))
    events.sort(key=lambda x: (x[0], x[1]))
    issues, errors = collections.OrderedDict(), collections.Counter()

    def cmp(exp, got, path):
        if isinstance(exp, dict):
            if not isinstance(got, dict):
                issues.setdefault(path, "type")
                return
            for k in exp:
                if k not in got:
                    issues.setdefault(path + "." + k, "MISSING")
                elif k not in DYNAMIC:
                    cmp(exp[k], got[k], path + "." + k)
        elif isinstance(exp, list) and exp and isinstance(got, list) and got:
            cmp(exp[0], got[0], path + "[]")

    for _, _, e in events:
        path = e["path"].split("?")[0]
        fn = e["request"].get("FunctionName", "")
        if path == "/Client/PurchaseItem":
            s = game.load_state()
            s["Currency"].update({"PARTS": 99999, "FAZ_TOKENS": 99999})
            game.save_state(s)
        try:
            r = game.handle(path, e["request"])
        except Exception as ex:  # report, keep going
            errors["%s: %r" % (fn or path, ex)] += 1
            continue
        if r is None:
            issues.setdefault(path + " " + fn, "NO LOGIC")
            continue
        if fn not in RANDOM_CALLS:
            cmp(e["response"], r[1], fn or path)
    os.remove(game.STATE_FILE)
    for k, v in errors.items():
        print("EXCEPTION", v, k)
    for k, v in issues.items():
        print(v, k)
    print("requests %d, issues %d, exceptions %d" % (len(events), len(issues), sum(errors.values())))
    return 1 if issues or errors else 0


if __name__ == "__main__":
    sys.exit(main())
