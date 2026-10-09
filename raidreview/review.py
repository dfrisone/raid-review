import collections
import re
from urllib.parse import parse_qs, urlparse

from .tooltips import describe

RECAP_MS = 30000
NO_DAMAGE = "No damage logged"

PERSONAL = {
    48707: ("Anti-Magic Shell", 60), 48792: ("Icebound Fortitude", 120), 49039: ("Lichborne", 120), 55233: ("Vampiric Blood", 90),
    198589: ("Blur", 60), 196555: ("Netherwalk", 180), 22812: ("Barkskin", 60), 61336: ("Survival Instincts", 180),
    22842: ("Frenzied Regeneration", 36), 363916: ("Obsidian Scales", 90), 374348: ("Renewing Blaze", 90),
    186265: ("Aspect of the Turtle", 180), 264735: ("Survival of the Fittest", 90), 109304: ("Exhilaration", 120),
    45438: ("Ice Block", 240), 414658: ("Ice Cold", 240), 55342: ("Mirror Image", 120), 235450: ("Prismatic Barrier", 25),
    11426: ("Ice Barrier", 25), 235313: ("Blazing Barrier", 25), 342245: ("Alter Time", 50),
    115203: ("Fortifying Brew", 120), 122470: ("Touch of Karma", 90), 122783: ("Diffuse Magic", 90),
    642: ("Divine Shield", 300), 498: ("Divine Protection", 60), 184662: ("Shield of Vengeance", 90), 31850: ("Ardent Defender", 90),
    86659: ("Guardian of Ancient Kings", 180), 471195: ("Lay on Hands", 420), 19236: ("Desperate Prayer", 90), 47585: ("Dispersion", 120),
    31224: ("Cloak of Shadows", 120), 5277: ("Evasion", 120), 1966: ("Feint", 15), 185311: ("Crimson Vial", 30),
    108271: ("Astral Shift", 90), 104773: ("Unending Resolve", 180), 108416: ("Dark Pact", 60),
    23920: ("Spell Reflection", 25), 118038: ("Die by the Sword", 120), 184364: ("Enraged Regeneration", 120),
}
STONES = {6262, 452930}
HEALTH_POTS = {1234768, 1295247, 1262857, 431416, 431419}
COMBAT_POTS = {1236994, 1236648}
EXTERNALS = {6940: "Blessing of Sacrifice", 102342: "Ironbark", 47788: "Guardian Spirit", 33206: "Pain Suppression",
             116849: "Life Cocoon", 357170: "Time Dilation", 1022: "Blessing of Protection"}
TRACKED = set(PERSONAL) | STONES | HEALTH_POTS | COMBAT_POTS | set(EXTERNALS)

# starting avoidable lists per encounter; users change them in the app
AVOID_DEFAULTS = {
    3420: ["Tempest", "Virulence", "Caustic Claws", "Caustic Residue", "Raging Crosswinds", NO_DAMAGE, "Mutilate",
           "Mutilated Gash", "Falling"],
}
NO_DAMAGE_NOTES = {
    3420: "On Sszorak this is a Viscous Cyst or Raging Crosswinds knock off the platform.",
}

DIFFICULTY = {1: "LFR", 3: "Normal", 4: "Heroic", 5: "Mythic"}


def parse_report(text):
    """Accepts a report link or a bare code; returns (code, boss, difficulty, mode) with unknowns as None."""
    text = text.strip()
    m = re.search(r"/reports/([A-Za-z0-9]{16})", text)
    if not m:
        if re.fullmatch(r"[A-Za-z0-9]{16}", text):
            return text, None, None, None
        raise ValueError("That doesn't look like a Warcraft Logs report link.")
    q = parse_qs(urlparse(text).query)
    one = lambda k: int(q[k][0]) if q.get(k, [""])[0].lstrip("-").isdigit() else None
    mode = "wipes" if q.get("wipes") else "kills" if q.get("kills") else None
    return m.group(1), one("boss"), one("difficulty"), mode


def overview(client, code):
    d = client.gql("""query($c:String){ reportData { report(code:$c) {
        title startTime zone { name } owner { name } guild { name server { name } }
        fights { id encounterID name difficulty kill startTime endTime bossPercentage } } } }""", {"c": code})
    rep = d["reportData"]["report"]
    if rep is None:
        raise ValueError("Report not found.")
    groups = {}
    for f in rep["fights"]:
        if not f["encounterID"]:
            continue
        g = groups.setdefault((f["encounterID"], f["difficulty"]), {
            "encounter": f["encounterID"], "difficulty": f["difficulty"], "name": f["name"],
            "difficultyName": DIFFICULTY.get(f["difficulty"], str(f["difficulty"])), "kills": 0, "wipes": 0, "best": 100})
        g["kills" if f["kill"] else "wipes"] += 1
        g["best"] = min(g["best"], 0 if f["kill"] else f["bossPercentage"] or 100)
    return {"code": code, "title": rep["title"], "startTime": rep["startTime"], "zone": (rep["zone"] or {}).get("name"),
            "guild": (rep["guild"] or {}).get("name"), "owner": (rep["owner"] or {}).get("name"),
            "encounters": sorted(groups.values(), key=lambda g: (g["encounter"], g["difficulty"]))}


def _report(client, code, body):
    return client.gql('{ reportData { report(code:"%s") { %s } } }' % (code, body))


def build(client, code, encounter, difficulty, mode, progress=lambda stage, done, total: None):
    progress("Reading the report", 0, 1)
    d = _report(client, code, """title startTime zone { name } guild { name }
        fights { id encounterID name difficulty kill startTime endTime bossPercentage }
        masterData { actors { id name type subType petOwner } abilities { gameID name } }""")
    rep = d["reportData"]["report"]
    fights = [f for f in rep["fights"] if f["encounterID"] == encounter and f["difficulty"] == difficulty
              and (mode == "all" or f["kill"] == (mode == "kills"))]
    if not fights:
        raise ValueError("No pulls match that boss, difficulty and kill/wipe choice.")
    fights.sort(key=lambda f: f["startTime"])
    byid = {f["id"]: f for f in fights}
    fids = [f["id"] for f in fights]
    abil = {a["gameID"]: a["name"] for a in rep["masterData"]["abilities"]}
    actors = {a["id"]: a for a in rep["masterData"]["actors"]}
    friendly = {i for i, a in actors.items() if a["type"] in ("Player", "Pet")}

    deaths = []
    for i in range(0, len(fids), 8):
        chunk = fids[i:i + 8]
        progress("Finding deaths", i, len(fids))
        r = _report(client, code, " ".join(f"f{x}: table(dataType:Deaths, fightIDs:[{x}])" for x in chunk))["reportData"]["report"]
        for x in chunk:
            deaths += r[f"f{x}"]["data"]["entries"]
    deaths.sort(key=lambda x: (fids.index(x["fight"]), x["timestamp"]))

    progress("Reading roles", 0, 1)
    role = {}
    r = _report(client, code, " ".join(f"f{x}: playerDetails(fightIDs:[{x}])" for x in fids))["reportData"]["report"]
    for x in fids:
        for rname, lst in r[f"f{x}"]["data"]["playerDetails"].items():
            for p in lst:
                role[(x, p["id"])] = (rname, (p.get("specs") or [{}])[0].get("spec", ""))

    casts, start = [], 0
    while start is not None:
        progress("Reading defensive casts", len(casts), len(casts) + 1)
        r = client.gql("query($s:Float){ reportData { report(code:\"%s\") { events(fightIDs:%s, startTime:$s, dataType:Casts, "
                       "hostilityType:Friendlies, filterExpression:\"ability.id in (%s)\", limit:10000){ data nextPageTimestamp } } } }"
                       % (code, fids, ",".join(map(str, sorted(TRACKED)))), {"s": start})
        ev = r["reportData"]["report"]["events"]
        casts += ev["data"]
        start = ev["nextPageTimestamp"]

    windows = []
    for i in range(0, len(deaths), 10):
        chunk = deaths[i:i + 10]
        progress("Reading death recaps", i, len(deaths))
        parts = []
        for j, x in enumerate(chunk):
            s, e = x["timestamp"] - RECAP_MS, x["timestamp"] + 50
            parts.append(f'd{j}: events(fightIDs:[{x["fight"]}], startTime:{s}, endTime:{e}, dataType:DamageTaken, sourceID:{x["id"]}, includeResources:true, limit:5000){{data}} '
                         f'h{j}: events(fightIDs:[{x["fight"]}], startTime:{s}, endTime:{e}, dataType:Healing, targetID:{x["id"]}, includeResources:true, limit:5000){{data}}')
        r = _report(client, code, " ".join(parts))["reportData"]["report"]
        for j in range(len(chunk)):
            windows.append((r[f"d{j}"]["data"], r[f"h{j}"]["data"]))

    progress("Reading damage taken", 0, 1)
    t = _report(client, code, f"table(dataType:DamageTaken, viewBy:Ability, fightIDs:{fids})")["reportData"]["report"]["table"]
    hostile = {e["guid"] for e in t["data"]["entries"]
               if e.get("actorType") in ("Boss", "NPC") and e["name"] != "Shadow Word: Death"}

    out_deaths = _deaths(deaths, windows, byid, abil, actors, friendly, role, casts, encounter)
    wipe = _wipes(out_deaths, fights)
    for x in out_deaths:
        w = wipe.get(x["f"])
        x["late"] = not byid[x["f"]]["kill"] and ((w is not None and x["ts"] >= w) or x["ord"] > 5)

    dmg = {}
    for i in range(0, len(fights), 8):
        chunk = fights[i:i + 8]
        progress("Reading damage taken", i, len(fights))
        parts = []
        for f in chunk:
            parts.append(f'all{f["id"]}: table(dataType:DamageTaken, fightIDs:[{f["id"]}])')
            if wipe.get(f["id"]) is not None:
                parts.append(f'pre{f["id"]}: table(dataType:DamageTaken, fightIDs:[{f["id"]}], startTime:{f["startTime"]}, '
                             f'endTime:{f["startTime"] + int(wipe[f["id"]] * 1000)})')
        r = _report(client, code, " ".join(parts))["reportData"]["report"]
        for f in chunk:
            out = {}
            for key in ("all", "pre"):
                tbl = r.get(f'{key}{f["id"]}') or r[f'all{f["id"]}']
                rows = {}
                for e in tbl["data"]["entries"]:
                    ab = {a["name"]: a["total"] for a in e["abilities"] if a["guid"] in hostile and a["total"]}
                    if ab:
                        rows[e["name"]] = [e["type"], e["icon"].split("-", 1)[-1], ab]
                out[key] = rows
            dmg[str(f["id"])] = out

    names, srcs = _pack_events(out_deaths)
    progress("Looking up ability descriptions", 0, 1)
    ability_ids = collections.defaultdict(list)
    for gid, name in abil.items():
        ability_ids[name].append(gid)
    wanted = set(names) | {x["kb"] for x in out_deaths} | {n for x in out_deaths for n in [y["n"] for y in x["defs"] + x["ext"]]}
    wanted |= {a for v in dmg.values() for k in v.values() for row in k.values() for a in row[2]}
    for gid, (name, _) in PERSONAL.items():
        ability_ids[name].append(gid)
    ability_ids["Healthstone"] = [6262]
    ability_ids["Health potion"] = sorted(HEALTH_POTS)
    tips = describe({n: sorted(ability_ids.get(n, []), key=lambda g: g not in hostile) for n in wanted if n != NO_DAMAGE},
                    lambda done, total: progress("Looking up ability descriptions", done, total))
    tips[NO_DAMAGE] = {"d": "Not a spell. No killing blow was logged and the player still had health. That usually means a knock off "
                            "the platform, a fall, or a scripted instant kill. " + NO_DAMAGE_NOTES.get(encounter, "")}

    pulls = [{"n": i + 1, "id": f["id"], "dur": round((f["endTime"] - f["startTime"]) / 1000), "kill": f["kill"],
              "boss": 0 if f["kill"] else (f["bossPercentage"] or 100), "wipe": wipe.get(f["id"]),
              "start": f["startTime"], "end": f["endTime"]} for i, f in enumerate(fights)]
    review = {
        "meta": {"code": code, "title": rep["title"], "zone": (rep["zone"] or {}).get("name"), "guild": (rep["guild"] or {}).get("name"),
                 "date": rep["startTime"], "encounter": encounter, "boss": fights[0]["name"], "difficulty": difficulty,
                 "difficultyName": DIFFICULTY.get(difficulty, str(difficulty)), "mode": mode},
        "pulls": pulls, "deaths": out_deaths, "dmg": dmg, "tips": tips, "evNames": names, "evSrcs": srcs,
        "recapWindow": RECAP_MS // 1000, "noDamage": NO_DAMAGE,
        "avoid": AVOID_DEFAULTS.get(encounter, [NO_DAMAGE, "Falling"]),
    }
    review["summary"] = summarize(review)
    progress("Done", 1, 1)
    return review


def _deaths(deaths, windows, byid, abil, actors, friendly, role, casts, encounter):
    by_src = collections.defaultdict(list)
    ever = collections.defaultdict(set)
    on_target = collections.defaultdict(list)
    for c in casts:
        if c.get("fight") not in byid:
            continue
        by_src[(c["fight"], c["sourceID"])].append(c)
        ever[c["sourceID"]].add(c["abilityGameID"])
        if c["abilityGameID"] in EXTERNALS and c.get("targetID"):
            on_target[(c["fight"], c["targetID"])].append(c)

    # shortest gap between two casts by the same player, to pick up talented cooldowns
    gap = {}
    for (fid, sid), cs in by_src.items():
        last = {}
        for c in sorted(cs, key=lambda c: c["timestamp"]):
            a = c["abilityGameID"]
            if a in last:
                gap[(sid, a)] = min(gap.get((sid, a), 1e9), (c["timestamp"] - last[a]) / 1000)
            last[a] = c["timestamp"]

    healer_deaths = collections.defaultdict(list)
    for x in deaths:
        if role.get((x["fight"], x["id"]), ("",))[0] == "healers":
            healer_deaths[x["fight"]].append((x["timestamp"], x["id"]))

    out = []
    order = collections.defaultdict(int)
    for x, (wdmg, wheal) in zip(deaths, windows):
        fid, pid, ts = x["fight"], x["id"], x["timestamp"]
        ev = []
        for e in wdmg:
            if e.get("type") == "damage" and e.get("targetID") == pid and e.get("sourceID") not in friendly:
                ev.append({"t": round((e["timestamp"] - ts) / 1000, 2), "k": 0, "a": abil.get(e["abilityGameID"], str(e["abilityGameID"])),
                           "amt": e.get("amount", 0) + e.get("absorbed", 0), "abs": e.get("absorbed", 0),
                           "hp": e.get("hitPoints"), "max": e.get("maxHitPoints")})
        for e in wheal:
            if e.get("type") == "heal" and e.get("amount") and e.get("targetID") == pid:
                ev.append({"t": round((e["timestamp"] - ts) / 1000, 2), "k": 1, "a": abil.get(e["abilityGameID"], str(e["abilityGameID"])),
                           "amt": e["amount"], "abs": 0, "hp": e.get("hitPoints"), "max": e.get("maxHitPoints"),
                           "src": actors.get(e.get("sourceID"), {}).get("name", "")})
        ev.sort(key=lambda e: e["t"])
        dmg = [e for e in ev if e["k"] == 0]
        maxhp = max([e["max"] for e in ev if e.get("max")] or [0])
        kb = (x.get("killingBlow") or {}).get("name")
        if not kb:
            known = [e for e in ev if e.get("hp") is not None and e.get("max")]
            if not known or (known[-1]["hp"] / known[-1]["max"] > 0.3 and known[-1]["t"] > -2):
                kb = NO_DAMAGE
            else:
                kb = dmg[-1]["a"] if dmg else "Unknown"
        heal5 = sum(e["amt"] for e in ev if e["k"] == 1 and e["t"] >= -5) + sum(e["abs"] for e in dmg if e["t"] >= -5)
        dmg5 = sum(e["amt"] for e in dmg if e["t"] >= -5)

        prior = [c for c in by_src[(fid, pid)] if c["timestamp"] <= ts]
        defs = []
        for a, (name, base) in PERSONAL.items():
            if a not in ever[pid]:
                continue
            cd = min(base, gap.get((pid, a), 1e9))
            used = [c["timestamp"] for c in prior if c["abilityGameID"] == a]
            if used and ts - used[-1] < 6000:
                st, note = "used", f"pressed {(ts - used[-1]) / 1000:.1f}s before death"
            elif used and ts - used[-1] < cd * 1000:
                st, note = "cd", f"used {(ts - used[-1]) / 1000:.0f}s earlier, ~{cd:.0f}s cooldown"
            else:
                st, note = "ready", "not used this pull" if not used else f"last used {(ts - used[-1]) / 1000:.0f}s earlier"
            defs.append({"n": name, "s": st, "note": note})
        if ever[pid] & STONES:
            used = [c["timestamp"] for c in prior if c["abilityGameID"] in STONES]
            defs.append({"n": "Healthstone", "s": "used" if used and ts - used[-1] < 6000 else "cd" if used else "ready",
                         "note": f"used {(ts - used[-1]) / 1000:.0f}s earlier" if used else "not used this pull"})
        if ever[pid] & HEALTH_POTS:
            used = [c for c in prior if c["abilityGameID"] in HEALTH_POTS | COMBAT_POTS]
            last = used[-1] if used else None
            defs.append({"n": "Health potion",
                         "s": "used" if last and ts - last["timestamp"] < 6000 and last["abilityGameID"] in HEALTH_POTS else "cd" if last else "ready",
                         "note": f'{abil.get(last["abilityGameID"])}, {(ts - last["timestamp"]) / 1000:.0f}s earlier' if last else "no potion used this pull"})
        ext = [{"n": EXTERNALS[c["abilityGameID"]], "by": actors.get(c["sourceID"], {}).get("name", ""), "t": round((c["timestamp"] - ts) / 1000, 1)}
               for c in on_target[(fid, pid)] if -12000 <= c["timestamp"] - ts <= 0]

        healers = {i for (ff, i), r in role.items() if ff == fid and r[0] == "healers"}
        # a healer who dies again after this death was battle-rezzed at some point; count them as alive
        dead = {h for t, h in healer_deaths[fid] if t < ts} - {h for t, h in healer_deaths[fid] if t > ts}
        order[fid] += 1
        r, spec = role.get((fid, pid), ("dps", ""))
        out.append({"f": fid, "p": x["name"], "id": pid, "cls": actors.get(pid, {}).get("subType", x.get("type", "")), "spec": spec,
                    "role": r, "at": ts, "ts": round((ts - byid[fid]["startTime"]) / 1000, 1), "ord": order[fid], "kb": kb,
                    "ok": x.get("overkill", 0), "max": maxhp, "h5": heal5, "d5": dmg5, "healers": [len(healers - dead), len(healers)],
                    "defs": defs, "ext": ext, "ev": ev,
                    "dmgBy": [[a["name"], a["total"]] for a in x["damage"]["abilities"][:5]]})
    return out


def _wipes(deaths, fights):
    # a wipe is the first moment five or more players die within three seconds
    wipe = {}
    for f in fights:
        if f["kill"]:
            continue
        ts = sorted(d["ts"] for d in deaths if d["f"] == f["id"])
        for i in range(len(ts) - 4):
            if ts[i + 4] - ts[i] <= 3:
                wipe[f["id"]] = ts[i]
                break
    return wipe


def _pack_events(deaths):
    # events become [t, kind (0 damage, 1 heal), ability index, amount, absorbed, hp, source index]
    names, srcs, ni, si = [], [], {}, {}

    def idx(table, lookup, v):
        if v not in lookup:
            lookup[v] = len(table)
            table.append(v)
        return lookup[v]

    for d in deaths:
        d["e"] = [[e["t"], e["k"], idx(names, ni, e["a"]), e["amt"], e["abs"], e["hp"],
                   idx(srcs, si, e["src"]) if e.get("src") else -1] for e in d.pop("ev")]
    return names, srcs


def judge(d, avoid=()):
    nd = d["kb"] == NO_DAMAGE
    flags = []
    if d["kb"] in avoid:
        flags.append("avoid")
    if nd:
        flags.append("ko")
    if not nd and any(x["s"] == "ready" for x in d["defs"]) and d["ok"] < d["max"] * 0.45:
        flags.append("def")
    if not nd and d["h5"] < d["max"] * 0.1:
        flags.append("heal")
    return flags


def summarize(review):
    """Per-player numbers for comparing nights. Avoidable damage stays per ability so the app can apply the current list."""
    players = {}
    for fid, v in review["dmg"].items():
        for name, (cls, spec, abs_) in v["pre"].items():
            p = players.setdefault(name, {"cls": cls, "spec": spec, "pulls": 0, "deaths": 0, "defReady": 0, "noHeals": 0, "kb": {}, "abs": {}})
            p["pulls"] += 1
            for a, amt in abs_.items():
                p["abs"][a] = p["abs"].get(a, 0) + amt
    for d in review["deaths"]:
        if d["late"]:
            continue
        p = players.setdefault(d["p"], {"cls": d["cls"], "spec": d["spec"], "pulls": 0, "deaths": 0, "defReady": 0, "noHeals": 0, "kb": {}, "abs": {}})
        f = judge(d)
        p["deaths"] += 1
        p["defReady"] += "def" in f
        p["noHeals"] += "heal" in f
        p["kb"][d["kb"]] = p["kb"].get(d["kb"], 0) + 1
    pulls = review["pulls"]
    return {"pulls": len(pulls), "kills": sum(p["kill"] for p in pulls), "best": min(p["boss"] for p in pulls),
            "deathsBeforeWipe": sum(1 for d in review["deaths"] if not d["late"]), "players": players}
