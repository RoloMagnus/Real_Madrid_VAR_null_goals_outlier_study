"""Unified table of goals ruled out ON THE PITCH (no VAR review) for all teams, from Flashscore commentary.

Phrasings captured (all name the player and team):
  1. '<P> (<T>) puts the ball into the net, but he is flagged for offside.'      -> offside (assistant flag)
  2. 'A goal, which was scored by <P> (<T>), was disallowed due to <reason>.'     -> offside / other
  3. 'Goal disallowed! <P> (<T>) scores but <ref> blows his whistle for a foul.'  -> foul
  4. 'The ball is in the net but it's immediately ruled out by referee <R> due to a <foul|handball>, much to the
      disappointment of the <P> (<T>) and his team.'                              -> foul / handball
  5. '<P> (<T>) thought he had scored but it was disallowed as ...'              -> other
Lines mentioning VAR are excluded, and events within 4 minutes of an existing VAR-confirmed Goal Disallowed
incident for the same team are treated as the same event (already in the VAR dataset).
Output: data/processed/onfield_disallowed_events.csv
"""
import importlib.util
import json
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
spec = importlib.util.spec_from_file_location("build03", os.path.join(ROOT, "scripts", "03_build_dataset.py"))
b3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b3)
b5spec = importlib.util.spec_from_file_location("enrich05", os.path.join(ROOT, "scripts", "05_enrich.py"))
b5 = importlib.util.module_from_spec(b5spec)
b5spec.loader.exec_module(b5)

PATS = [
    ("flag", re.compile(r"(?P<p>[^.]+?) \((?P<t>[^)]+)\) puts the ball into the net, but (?:he|she) is flagged for offside", re.I), "Offside"),
    ("goal_disallowed_line", re.compile(r"A goal, which was scored by (?P<p>.+?) \((?P<t>[^)]+)\), was disallowed due to (?P<r>[a-z ]+)", re.I), None),
    ("whistle_foul", re.compile(r"Goal disallowed! (?P<p>.+?) \((?P<t>[^)]+)\) scores but .*? blows his whistle for a (?P<r>foul)", re.I), None),
    ("ruled_out", re.compile(r"immediately ruled out by referee .*? due to an? (?P<r>[a-z ]+?),? much to the disappointment of the (?P<p>.+?) \((?P<t>[^)]+)\)", re.I), None),
    ("thought_scored", re.compile(r"(?P<p>[^.]+?) \((?P<t>[^)]+)\) thought he had scored but it was disallowed as (?P<r>.+?)\.", re.I), "Other"),
]


def reason_of(r):
    r = (r or "").lower()
    return "Offside" if "offside" in r else "Foul" if "foul" in r else "Handball" if "hand" in r else "Other"


def players_dict():
    pl = {}
    es = pd.read_csv(os.path.join(RAW, "espn_matches.csv"), dtype={"event_id": str})
    for eid in es[es.status == "Full Time"].event_id:
        d = json.load(open(os.path.join(RAW, "espn_cache", f"summary_{eid}.json"), encoding="utf8"))
        for ro in d.get("rosters") or []:
            for a in ro.get("roster") or []:
                nm = (a.get("athlete") or {}).get("displayName")
                if nm:
                    pl[b5.tokens(nm)] = nm
    return pl


def main():
    ms = pd.read_csv(os.path.join(OUT, "matches_ref.csv")).set_index("fs_id")
    tm = pd.read_csv(os.path.join(OUT, "team_match.csv")).set_index(["fs_id", "team"])
    var = pd.read_csv(os.path.join(OUT, "disallowed_goals_all.csv"))
    var["mn"] = var.minute.map(b3.minute_num)
    vk = {}
    for r in var.itertuples():
        vk.setdefault((r.fs_id, r.team), []).append(r.mn)
    players = players_dict()

    ev = []
    for fs_id, m in ms.iterrows():
        txt = open(os.path.join(RAW, "fs_cache", f"df_lc_{fs_id}.txt"), encoding="utf8").read()
        for rec in txt.split("~")[1:]:
            d, _ = b3.fields(rec)
            t = d.get("MD", "")
            if not t or re.search(r"\bVAR\b|video assistant", t, re.I):
                continue
            for kind, rx, fixed in PATS:
                s = rx.search(t)
                if not s:
                    continue
                team = b3.norm_team(s.group("t").strip())
                if team not in (m.home, m.away):
                    break
                reason = fixed or reason_of(s.groupdict().get("r"))
                ev.append(dict(fs_id=fs_id, team=team, kind=kind, minute=d.get("MB"), mn=b3.minute_num(d.get("MB")),
                               player_short=s.group("p").strip().split(". ")[-1], reason=reason, text=t[:300]))
                break
    e = pd.DataFrame(ev)
    print("raw matched lines:", len(e), e.kind.value_counts().to_dict())
    # drop events already in the VAR dataset (same team, within 4 minutes)
    e["in_var_dataset"] = [any(abs(mn - x) <= 4 for x in vk.get((f, t), [])) for f, t, mn in zip(e.fs_id, e.team, e.mn)]
    e = e[~e.in_var_dataset].copy()
    # same goal described by several phrasings -> keep one (same match + team + minute within 2)
    e = e.sort_values(["fs_id", "team", "mn"])
    keep, last = [], {}
    prio = {"flag": 0, "ruled_out": 1, "whistle_foul": 2, "thought_scored": 3, "goal_disallowed_line": 4}
    for r in e.itertuples():
        k = (r.fs_id, r.team)
        if k in last and abs(r.mn - last[k][0]) <= 2:
            if prio[r.kind] < prio[last[k][1]]:
                keep[last[k][2]] = False
                last[k] = (r.mn, r.kind, len(keep))
                keep.append(True)
            else:
                keep.append(False)
            continue
        last[k] = (r.mn, r.kind, len(keep))
        keep.append(True)
    e = e[keep].copy()
    print("on-field disallowed goals after dedupe:", len(e), e.reason.value_counts().to_dict())

    rows = []
    for r in e.itertuples():
        m = ms.loc[r.fs_id]
        home = r.team == m.home
        opp = m.away if home else m.home
        inc = b3.parse_incidents(b3.read("df_sui", r.fs_id))
        sh = sa = 0
        for x in inc:
            if x.get("sh") is not None and x["minute"] and b3.minute_num(x["minute"]) is not None and b3.minute_num(x["minute"]) <= r.mn:
                sh, sa = int(x["sh"]), int(x["sa"])
        tg, og = (m.home_goals, m.away_goals) if home else (m.away_goals, m.home_goals)
        sb_t, sb_o = (sh, sa) if home else (sa, sh)
        tr = tm.loc[(r.fs_id, r.team)]
        orow = tm.loc[(r.fs_id, opp)]
        played = tr.played_before
        slug = r.player_short
        pf = players.get(b5.tokens(slug), slug)
        rows.append(dict(
            fs_id=r.fs_id, date=m.date, season=m.season, round=int(re.search(r"\d+", str(m["round"])).group()),
            team=r.team, rival=opp, local_flag=home, active_player=pf, reason=r.reason, kind=r.kind,
            minute=r.mn, minute_display=r.minute, half="first" if r.mn <= 45 else "second",
            score_before_goal=f"{sb_t}-{sb_o}",
            goal_would_have_been="Reduce deficit" if sb_t - sb_o < -1 else "Equaliser" if sb_t - sb_o == -1 else "Go-ahead / opener" if sb_t == sb_o else "Extend lead",
            team_goals_final=int(tg), rival_goals_final=int(og),
            outcome="WIN" if tg > og else "DRAW" if tg == og else "LOSS",
            points_lost=(3 if tg + 1 > og else 1 if tg + 1 == og else 0) - (3 if tg > og else 1 if tg == og else 0),
            league_position_at_time=None if played == 0 else tr.pos_before, rival_position_at_time=None if played == 0 else orow.pos_before,
            points_at_time=tr.pts_before, referee_on_field=m.referee, commentary=r.text, season_final_pos=tr.final_pos))
    out = pd.DataFrame(rows).sort_values(["date", "minute"]).reset_index(drop=True)
    out.insert(0, "rank", out.index + 1)
    out.to_csv(os.path.join(OUT, "onfield_disallowed_events.csv"), index=False, encoding="utf-8-sig")
    print(out.team.value_counts().head(10).to_dict())
    print(out[out.team == "Real Madrid"][["date", "rival", "active_player", "minute", "reason"]].to_string())


if __name__ == "__main__":
    main()
