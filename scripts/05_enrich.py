"""Enrich the Flashscore-derived data with: ESPN cross-reference (referee full names, accented player
names, independent VAR corroboration), table position before each match, xG (Understat),
final-table based Top-10 flags and context categories for each disallowed goal.

Outputs (data/processed): team_match.csv, disallowed_goals_enriched.csv, team_season.csv, espn_matches.csv
"""
import glob
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")


def strip_acc(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c))


def tokens(s):
    return frozenset(re.findall(r"[a-z]+", strip_acc(s).lower()))


# ------------------------------------------------------------------ ESPN cross-reference
def load_espn():
    ms = pd.read_csv(os.path.join(RAW, "espn_matches.csv"), dtype={"event_id": str})
    ms = ms[ms.status == "Full Time"].copy()
    rows, players = [], {}
    for r in ms.itertuples():
        d = json.load(open(os.path.join(RAW, "espn_cache", f"summary_{r.event_id}.json"), encoding="utf8"))
        offs = [o.get("fullName") or o.get("displayName") for o in (d.get("gameInfo") or {}).get("officials", [])
                if (o.get("position") or {}).get("name") == "Referee"]
        for ro in d.get("rosters") or []:
            for a in ro.get("roster") or []:
                nm = (a.get("athlete") or {}).get("displayName")
                if nm:
                    players[tokens(nm)] = nm
        ev = []  # explicit VAR overturned goals / decisions and offside flags
        for c in d.get("commentary") or []:
            t = (c.get("text") or "")
            ty = ((c.get("play") or {}).get("type") or {}).get("text") or ""
            if ty == "Deleted After Review" and t.startswith("GOAL OVERTURNED"):
                ev.append(("overturned", (c.get("time") or {}).get("displayValue"), t))
            elif ty.startswith("VAR") and "No Goal" in t:
                ev.append(("no_goal", (c.get("time") or {}).get("displayValue"), t))
            elif ty == "Offside":
                ev.append(("offside", (c.get("time") or {}).get("displayValue"), t))
            elif "Video Review" in t or (ty.startswith("VAR") and "Goal" in ty):
                ev.append(("review", (c.get("time") or {}).get("displayValue"), t))
        rows.append(dict(event_id=r.event_id, kickoff_utc=pd.Timestamp(r.date_utc).tz_localize(None),
                         referee=offs[0] if offs else None, home_goals=int(r.home_goals), away_goals=int(r.away_goals),
                         espn_var_events=json.dumps(ev, ensure_ascii=False)))
    return pd.DataFrame(rows), players


def attach_espn(matches, espn):
    matches = matches.copy()
    matches["kickoff_utc"] = pd.to_datetime(matches.date_utc)
    esp = espn.copy()
    esp["k"] = esp.kickoff_utc.dt.floor("h")
    matches["k"] = matches.kickoff_utc.dt.floor("h")
    m = matches.merge(esp, on=["k", "home_goals", "away_goals"], how="left", suffixes=("", "_espn"))
    m = m.drop_duplicates("fs_id", keep=False) if m.fs_id.duplicated().any() else m
    return m


# ------------------------------------------------------------------ league table
def table_before(tm):
    """Position / points of each team before every one of its matches (pts, GD, GF tiebreak)."""
    res = []
    for season, g in tm.groupby("season"):
        g = g.sort_values("kickoff")
        pts, gd, gf, played = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
        teams = set(g.team)
        for ko, grp in g.groupby("kickoff", sort=True):
            order = sorted(teams, key=lambda t: (-pts[t], -gd[t], -gf[t], t))
            rank = {t: i + 1 for i, t in enumerate(order)}
            for r in grp.itertuples():
                res.append((r.Index, rank[r.team], pts[r.team], played[r.team]))
            for r in grp.itertuples():
                p = 3 if r.gf > r.ga else 1 if r.gf == r.ga else 0
                pts[r.team] += p
                gd[r.team] += r.gf - r.ga
                gf[r.team] += r.gf
                played[r.team] += 1
    idx, pos, pt, pl = zip(*res)
    s = pd.DataFrame({"pos_before": pos, "pts_before": pt, "played_before": pl}, index=idx)
    return tm.join(s)


def final_tables(tm):
    rows = []
    for season, g in tm.groupby("season"):
        agg = g.assign(pts=np.where(g.gf > g.ga, 3, np.where(g.gf == g.ga, 1, 0)), gd=g.gf - g.ga).groupby("team").agg(
            pts=("pts", "sum"), gd=("gd", "sum"), gf=("gf", "sum"), played=("gf", "size")).reset_index()
        agg = agg.sort_values(["pts", "gd", "gf"], ascending=False).reset_index(drop=True)
        agg["final_pos"] = agg.index + 1
        agg["season"] = season
        rows.append(agg)
    return pd.concat(rows)


# ------------------------------------------------------------------ xG join
UNDER_ALIAS = {"atleticomadrid": "atleticodemadrid", "barcelona": "fcbarcelona", "alaves": "deportivoalaves",
               "valladolid": "realvalladolid", "betis": "realbetis", "celtavigo": "celtadevigo",
               "athleticclub": "athleticclub", "leganes": "leganes"}


def key(n):
    k = re.sub(r"[^a-z]", "", strip_acc(n).lower())
    return UNDER_ALIAS.get(k, k)


def add_xg(tm):
    u = pd.read_csv(os.path.join(RAW, "understat_team_matches.csv"))
    u["k"] = u.team.map(key)
    u["date"] = pd.to_datetime(u.date)
    tm = tm.copy()
    tm["k"] = tm.team.map(key)
    tm["date"] = pd.to_datetime(tm.kickoff).dt.normalize()
    out = []
    for (season, k), g in tm.groupby(["season", "k"]):
        uu = u[(u.season == season) & (u.k == k)].sort_values("date")
        g = g.sort_values("date")
        mg = pd.merge_asof(g, uu[["date", "xg", "xga", "ppda_att", "ppda_def"]], on="date", direction="nearest",
                           tolerance=pd.Timedelta(days=2))
        out.append(mg)
    r = pd.concat(out).drop(columns="k")
    return r


# ------------------------------------------------------------------ disallowed-goal context
def classify(reason, text, offside_who):
    t = (text or "").lower()
    if reason == "handball" or (reason == "video review" and re.search(r"hand ?ball", t)):
        return "Handball (attacking team)"
    if reason == "Foul" or (reason == "video review" and re.search(r"\bfoul", t)):
        return "Attacking foul (before goal)"
    if reason == "offside" or (reason == "video review" and "offside" in t):
        if offside_who == "scorer":
            return "Offside - goalscorer"
        if offside_who == "teammate":
            return "Offside - teammate in build-up"
        return "Offside - player not identified"
    return "Other / unspecified VAR review"


DECISION_RE = re.compile(r"(?i)disallow|no goal|won.t count|not count|ruled out|goal is chalked")


def decision_sentence(var_text):
    lines = [x.strip() for x in str(var_text or "").split("||")]
    hits = [x for x in lines if DECISION_RE.search(x)]
    return hits[0] if hits else (lines[0] if lines and lines[0] != "nan" else "")


def offside_who(events_json, team, scorer, minute):
    """Who was flagged offside (ESPN feed): 'scorer', 'teammate' or None when no ESPN offside event matches."""
    if not isinstance(events_json, str) or not isinstance(scorer, str):
        return None, None
    stoks = tokens(scorer)
    for kind, mtxt, txt in json.loads(events_json):
        if kind != "offside":
            continue
        m = re.sub(r"[^0-9+]", "", str(mtxt or ""))
        mn = sum(int(x) for x in m.split("+") if x) if m else None
        if mn is None or abs(mn - minute) > 1:
            continue
        mt = re.match(r"Offside, (.+?)\.", txt or "")
        if not mt or key(mt.group(1)) not in key(team) and key(team) not in key(mt.group(1)):
            continue
        pl = re.search(r"(?:but |\. )([^.]+?) is caught offside", txt)
        if not pl:
            continue
        ptoks = tokens(pl.group(1))
        return ("scorer" if ptoks <= stoks or stoks <= ptoks else "teammate"), pl.group(1)
    return None, None


def goal_effect(row):
    before = (row.score_home - row.score_away) if row.venue == "Home" else (row.score_away - row.score_home)
    if before < -1:
        return "Reduce deficit"
    if before == -1:
        return "Equaliser"
    if before == 0:
        return "Go-ahead / opener"
    return "Extend lead"


def points(gf, ga):
    return 3 if gf > ga else 1 if gf == ga else 0


def main():
    matches = pd.read_csv(os.path.join(OUT, "matches.csv"))
    tm = pd.read_csv(os.path.join(OUT, "team_match_raw.csv"))
    dis = pd.read_csv(os.path.join(OUT, "disallowed_goals_all.csv"))
    base_min = dis.minute.str.extract(r"(\d+)")[0].astype(int)
    dis["half"] = np.where(base_min <= 45, 1, 2)  # stoppage time keeps the half's base minute (45+x / 90+x)
    tm["kickoff"] = pd.to_datetime(tm.kickoff)
    for c in ("red", "yellow"):
        tm[c] = tm[c].fillna(0)

    espn, players = load_espn()
    espn.to_csv(os.path.join(OUT, "espn_matches.csv"), index=False, encoding="utf-8-sig")
    rt = pd.read_csv(os.path.join(OUT, "referees_tm.csv"))
    ref_full = rt.set_index("fs_id").referee_tm

    # short -> full referee name map learned from paired matches (Transfermarkt full names)
    votes = defaultdict(Counter)
    for fs_id, full in ref_full.dropna().items():
        short = matches.set_index("fs_id").referee_short.get(fs_id)
        if isinstance(short, str):
            votes[short][full] += 1
    ref_map = {s: c.most_common(1)[0][0] for s, c in votes.items()}
    matches["referee"] = [ref_full.get(i) if isinstance(ref_full.get(i), str) else ref_map.get(s, s)
                          for i, s in zip(matches.fs_id, matches.referee_short)]
    matches.to_csv(os.path.join(OUT, "matches_ref.csv"), index=False, encoding="utf-8-sig")
    mm = matches.copy()
    mm["espn_var_events"] = None
    ev = espn.copy()
    ev["k"] = ev.kickoff_utc.dt.floor("h")
    mm["k"] = pd.to_datetime(mm.date_utc).dt.floor("h")
    mm = mm.merge(ev[["k", "home_goals", "away_goals", "espn_var_events"]], on=["k", "home_goals", "away_goals"],
                  how="left", suffixes=("", "_e"))
    mm["espn_var_events"] = mm.espn_var_events_e
    mm = mm.drop_duplicates("fs_id", keep=False)

    tm = tm.sort_values("kickoff").reset_index(drop=True)
    tm = table_before(tm)
    tm = add_xg(tm)
    tm["xg"] = tm.xg.fillna(tm.xg_fs)
    # own pressing = opponent passes (att) vs own defensive actions (def); opponent pressing taken from the other row of the same match
    opp = tm[["fs_id", "team", "ppda_att", "ppda_def"]].rename(
        columns={"team": "opponent", "ppda_att": "opp_ppda_att", "ppda_def": "opp_ppda_def"})
    tm = tm.merge(opp, on=["fs_id", "opponent"], how="left")
    tm["ppda"] = tm.ppda_att / tm.ppda_def
    tm["opp_ppda"] = tm.opp_ppda_att / tm.opp_ppda_def
    ft = final_tables(tm)
    ft["relegated"] = False
    top = ft.copy()
    top["top10"] = top.final_pos <= 10
    tm = tm.merge(top[["season", "team", "final_pos", "top10"]], on=["season", "team"], how="left")
    tm["pts"] = [points(a, b) for a, b in zip(tm.gf, tm.ga)]
    tm.to_csv(os.path.join(OUT, "team_match.csv"), index=False, encoding="utf-8-sig")
    ft.to_csv(os.path.join(OUT, "final_tables.csv"), index=False, encoding="utf-8-sig")

    # ---- enrich disallowed goals
    pos = tm.set_index(["fs_id", "team"])
    d = dis.copy()
    d["pos_before"] = [pos.loc[(a, b), "pos_before"] for a, b in zip(d.fs_id, d.team)]
    d["pts_before"] = [pos.loc[(a, b), "pts_before"] for a, b in zip(d.fs_id, d.team)]
    d["played_before"] = [pos.loc[(a, b), "played_before"] for a, b in zip(d.fs_id, d.team)]
    d["opp_pos_before"] = [pos.loc[(a, b), "pos_before"] for a, b in zip(d.fs_id, d.opponent)]
    d.loc[d.played_before == 0, ["pos_before", "opp_pos_before"]] = np.nan  # no table exists before round 1
    d["team_final_pos"] = [pos.loc[(a, b), "final_pos"] for a, b in zip(d.fs_id, d.team)]
    d["opp_final_pos"] = [pos.loc[(a, b), "final_pos"] for a, b in zip(d.fs_id, d.opponent)]
    d["referee_full"] = [ref_full.get(i) if isinstance(ref_full.get(i), str) else ref_map.get(s, s)
                         for i, s in zip(d.fs_id, d.ref_short)]
    d["referee_source"] = ["Transfermarkt" if isinstance(ref_full.get(i), str) else
                           ("Flashscore (name expanded)" if s in ref_map else "Flashscore (abbreviated)")
                           for i, s in zip(d.fs_id, d.ref_short)]

    def full_name(short, slug):
        if isinstance(slug, str):
            tk = tokens(slug)
            if tk in players:
                return players[tk]
        return slug if isinstance(slug, str) else short

    d["player_full"] = [full_name(a, b) for a, b in zip(d.player_short, d.player)]
    d["context_text"] = [decision_sentence(v) if isinstance(v, str) and v else (t if isinstance(t, str) else "")
                         for v, t in zip(d.var_commentary, d.fs_text)]
    e_events = mm.set_index("fs_id").espn_var_events
    who = [offside_who(e_events.get(i), t, p, mn) for i, t, p, mn in
           zip(d.fs_id, d.team, d.player_full, d.minute_num)]
    d["offside_player_espn"] = [w[1] for w in who]
    d["category"] = [classify(r, t, w[0]) for r, t, w in zip(d.reason_fs, d.context_text, who)]
    d["half_label"] = d.half.map({1: "1st half", 2: "2nd half"})
    d["goal_effect"] = d.apply(goal_effect, axis=1)
    fin = d.final.str.split("-", expand=True).astype(int)
    d["team_gf"] = np.where(d.venue == "Home", fin[0], fin[1])
    d["team_ga"] = np.where(d.venue == "Home", fin[1], fin[0])
    d["pts_actual"] = [points(a, b) for a, b in zip(d.team_gf, d.team_ga)]
    d["pts_if_allowed"] = [points(a + 1, b) for a, b in zip(d.team_gf, d.team_ga)]
    d["points_lost"] = d.pts_if_allowed - d.pts_actual
    d["result_changed"] = d.points_lost > 0
    d.to_csv(os.path.join(OUT, "disallowed_goals_enriched.csv"), index=False, encoding="utf-8-sig")

    # ---- ESPN corroboration of Flashscore events (2022-23+ where ESPN labels explicit overturns)
    e = mm.set_index("fs_id").espn_var_events
    def _mins(m):
        s = re.sub(r"[^0-9+]", "", str(m or ""))
        return sum(int(x) for x in s.split("+") if x) if s else None

    d["espn_corroborated"] = [
        any(k in ("overturned", "no_goal", "review") and _mins(m) is not None and abs(_mins(m) - mn) <= 3
            for k, m, _t in json.loads(e.get(i))) if isinstance(e.get(i), str) else None
        for i, mn in zip(d.fs_id, d.minute_num)]
    d.to_csv(os.path.join(OUT, "disallowed_goals_enriched.csv"), index=False, encoding="utf-8-sig")
    print("referee source:", d.referee_source.value_counts().to_dict())
    print("ESPN corroboration by season:\n", d.groupby("season").espn_corroborated.agg(["mean", "count"]))
    print(d.category.value_counts())
    print(tm.xg.isna().mean(), tm.pos_before.isna().mean())


if __name__ == "__main__":
    main()
