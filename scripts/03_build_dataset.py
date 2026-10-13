"""Build processed datasets from the Flashscore cache.

Outputs (data/processed):
  matches.csv                  one row per match (+ referee)
  team_match.csv               one row per team per match (shots, offsides, ... + table position before kickoff)
  disallowed_goals_all.csv     every 'Goal Disallowed' incident, all teams, with VAR flag/context
"""
import os
import re
import unicodedata

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
os.makedirs(OUT, exist_ok=True)

TEAM = {
    "Alaves": "Deportivo Alavés", "Almeria": "Almería", "Ath Bilbao": "Athletic Club",
    "Atl. Madrid": "Atlético de Madrid", "Barcelona": "FC Barcelona", "Betis": "Real Betis",
    "Cadiz CF": "Cádiz", "Celta Vigo": "Celta de Vigo", "Dep. A Coruna": "Deportivo La Coruña",
    "Granada CF": "Granada", "Leganes": "Leganés", "Malaga": "Málaga", "Valladolid": "Real Valladolid",
}
norm_team = lambda n: TEAM.get(n, n)


def fields(rec):
    """Split a feed record into a dict (first occurrence wins) and a list of all (k, v)."""
    pairs = [x.split("÷", 1) for x in rec.split("¬") if "÷" in x]
    d = {}
    for k, v in pairs:
        d.setdefault(k, v)
    return d, pairs


def read(feed, mid):
    p = os.path.join(RAW, "fs_cache", f"{feed}_{mid}.txt")
    return open(p, encoding="utf8").read() if os.path.exists(p) else ""


def minute_num(s):
    m = re.match(r"(\d+)(?:\+(\d+))?", s or "")
    return (int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0)) if m else None


def strip_acc(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


# ---------------------------------------------------------------- stats
STAT_MAP = {"Ball possession": "possession", "Total shots": "shots", "Shots on target": "sot",
            "Blocked shots": "blocked", "Shots off target": "shots_off", "Corner kicks": "corners",
            "Offsides": "offsides", "Fouls": "fouls", "Yellow cards": "yellow", "Red cards": "red",
            "Expected goals (xG)": "xg_fs", "Big chances": "big_chances",
            "Touches in opposition box": "box_touches", "Shots inside the box": "shots_in_box"}


def num(v):
    if v is None:
        return None
    m = re.match(r"-?\d+(\.\d+)?", v.replace("%", "").strip())
    return float(m.group(0)) if m else None


def parse_stats(txt):
    sec = ("~" + txt).split("~SE÷")
    match = next((s for s in sec if s.startswith("Match")), "")
    out = {}
    for rec in match.split("~SD÷")[1:]:
        d, _ = fields("SD÷" + rec)
        name = d.get("SG")
        if name in STAT_MAP:
            out[STAT_MAP[name]] = (num(d.get("SH")), num(d.get("SI")))
    return out


def parse_referee(txt):
    m = re.search(r"MIT÷REF¬MIV÷([^¬~]*)", txt)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------- incidents
def parse_incidents(txt):
    half, events = None, []
    for rec in txt.split("~")[1:]:
        d, pairs = fields(rec)
        if "AC" in d and rec.startswith("AC÷"):
            half = 1 if "1st" in d["AC"] else 2 if "2nd" in d["AC"] else half
            continue
        if rec.startswith("IIIX÷"):
            events.append(dict(kind=d.get("IKX"), side=d.get("IAX"), minute=d.get("IBX"), half=half,
                               player=d.get("IFX"), url=d.get("IU"), text=d.get("ICT"), reason=d.get("ILX")))
        elif rec.startswith("III÷"):
            k = d.get("IK")
            ev = dict(kind=k, side=d.get("IA"), minute=d.get("IB"), half=half, player=d.get("IF"),
                      url=d.get("IU"), text=d.get("ICT"), sh=d.get("INX"), sa=d.get("IOX"))
            events.append(ev)
    return events


def parse_commentary(txt):
    rows = []
    for rec in txt.split("~")[1:]:
        d, _ = fields(rec)
        if "MD" in d:
            rows.append(dict(minute=d.get("MB"), icon=d.get("MC"), text=d["MD"]))
    return rows


def slug_name(url):
    """'/player/mbappe-kylian/ID/' -> 'Kylian Mbappe' (Flashscore slugs are surname-first)."""
    m = re.match(r"/player/([^/]+)/", url or "")
    if not m:
        return None
    toks = m.group(1).split("-")
    return " ".join(t.capitalize() for t in toks[1:] + toks[:1]) if len(toks) > 1 else toks[0].capitalize()


def main():
    ms = pd.read_csv(os.path.join(RAW, "fs_matches.csv"))
    ms["home"] = ms.home.map(norm_team)
    ms["away"] = ms.away.map(norm_team)
    ts = pd.to_datetime(ms.date_utc).dt.tz_localize("UTC").dt.tz_convert("Europe/Madrid")
    ms["kickoff_local"] = ts.dt.tz_localize(None)
    ms["date"] = ts.dt.date
    ms["home_goals"] = ms.home_goals.astype(int)
    ms["away_goals"] = ms.away_goals.astype(int)

    tm_rows, refs, dis_rows = [], {}, []
    for r in ms.itertuples():
        st = parse_stats(read("df_st", r.fs_id))
        refs[r.fs_id] = parse_referee(read("df_sur", r.fs_id))
        for side, team, opp, gf, ga in (("H", r.home, r.away, r.home_goals, r.away_goals),
                                        ("A", r.away, r.home, r.away_goals, r.home_goals)):
            i = 0 if side == "H" else 1
            row = dict(season=r.season, fs_id=r.fs_id, kickoff=r.kickoff_local, team=team, opponent=opp,
                       venue=side, gf=gf, ga=ga)
            for k, v in st.items():
                row[k] = v[i]
            tm_rows.append(row)

        inc = parse_incidents(read("df_sui", r.fs_id))
        com = parse_commentary(read("df_lc", r.fs_id))
        for e in inc:
            if e["kind"] != "Goal Disallowed":
                continue
            prior = [x for x in inc[:inc.index(e)] if x.get("sh") is not None]
            sh, sa = (int(prior[-1]["sh"]), int(prior[-1]["sa"])) if prior else (0, 0)
            mn = minute_num(e["minute"])
            near = [c for c in com if c["minute"] and minute_num(c["minute"]) is not None and mn is not None
                    and mn - 1 <= minute_num(c["minute"]) <= mn + 3
                    and (c["icon"] == "var" or re.search(r"(?i)\bVAR\b|video (assistant|review)|disallow", c["text"]))]
            team = r.home if e["side"] == "1" else r.away
            opp = r.away if e["side"] == "1" else r.home
            dis_rows.append(dict(
                season=r.season, fs_id=r.fs_id, date=r.date, kickoff=r.kickoff_local, home=r.home, away=r.away,
                final=f"{r.home_goals}-{r.away_goals}", team=team, opponent=opp,
                venue="Home" if e["side"] == "1" else "Away", player_short=e["player"],
                player=slug_name(e["url"]), minute=e["minute"], minute_num=mn, half=e["half"],
                reason_fs=e["reason"], score_home=sh, score_away=sa, fs_text=e["text"],
                var_commentary=" || ".join(c["text"] for c in near),
                var_flag=bool(near) or "video assistant" in (e["text"] or "").lower(),
                ref_short=refs[r.fs_id]))

    matches = ms.copy()
    matches["referee_short"] = matches.fs_id.map(refs)
    matches.to_csv(os.path.join(OUT, "matches.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(tm_rows).to_csv(os.path.join(OUT, "team_match_raw.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(dis_rows).to_csv(os.path.join(OUT, "disallowed_goals_all.csv"), index=False, encoding="utf-8-sig")
    print("matches", len(matches), "team-matches", len(tm_rows), "disallowed", len(dis_rows))


if __name__ == "__main__":
    main()
