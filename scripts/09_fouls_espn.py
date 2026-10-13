"""Foul locations from ESPN match commentary.

ESPN logs two lines per foul: 'Foul by <player> (<team>).' and '<player> (<team>) wins a free kick in the
defensive half / attacking half / on the left|right wing' (or 'draws a foul in the penalty area').
The location is from the FOULED player's perspective, so for the team that committed the foul:
  fouled player's 'defensive half'  -> foul committed in the committer's ATTACKING half
  fouled player's 'attacking half'  -> foul committed in the committer's DEFENSIVE half
  'on the left/right wing'          -> wing (half not stated)
  'draws a foul in the penalty area'-> committer's own penalty area
Output: data/processed/espn_fouls.csv (one row per team-match, keyed by season + home + away + team)
"""
import json
import os
import re
import unicodedata

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")

kk = lambda s: re.sub(r"[^a-z]", "", "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c)).lower())
FOUL_BY = re.compile(r"^Foul by .*?\(([^)]+)\)")
FREE_KICK = re.compile(r"\(([^)]+)\) wins a free kick (in the defensive half|in the attacking half|on the left wing|on the right wing)")
PEN_CONCEDED = re.compile(r"^Penalty conceded by .*?\(([^)]+)\) after a foul")


def main():
    fs = pd.read_csv(os.path.join(OUT, "matches.csv"))
    canon = sorted(set(fs.home) | set(fs.away))

    def to_canon(n):
        k = kk(n)
        if k == "atleticomadrid":
            return "Atlético de Madrid"
        if k == "celtavigo":
            return "Celta de Vigo"
        for c in canon:
            if kk(c) == k:
                return c
        for c in canon:
            if k in kk(c) or kk(c) in k:
                return c
        return n

    es = pd.read_csv(os.path.join(RAW, "espn_matches.csv"), dtype={"event_id": str})
    es = es[es.status == "Full Time"]
    key = fs.set_index(["season", "home", "away"]).fs_id
    rows, miss = [], 0
    for r in es.itertuples():
        h, a = to_canon(r.home), to_canon(r.away)
        if (r.season, h, a) not in key.index:
            miss += 1
            continue
        fs_id = key[(r.season, h, a)]
        d = json.load(open(os.path.join(RAW, "espn_cache", f"summary_{r.event_id}.json"), encoding="utf8"))
        cnt = {t: dict(foul_lines=0, att_half=0, def_half=0, wing=0, own_box=0) for t in (h, a)}
        for c in d.get("commentary") or []:
            t = c.get("text") or ""
            ty = ((c.get("play") or {}).get("type") or {}).get("text") or ""
            if ty != "Foul":
                continue
            m = FOUL_BY.match(t)
            if m:
                tn = to_canon(m.group(1))
                if tn in cnt:
                    cnt[tn]["foul_lines"] += 1
                continue
            m = FREE_KICK.search(t)
            if m:
                winner = to_canon(m.group(1))
                if winner not in cnt:
                    continue
                committer = a if winner == h else h
                loc = m.group(2)
                cnt[committer]["att_half" if "defensive" in loc else "def_half" if "attacking" in loc else "wing"] += 1
                continue
            m = PEN_CONCEDED.match(t)
            if m:
                tn = to_canon(m.group(1))
                if tn in cnt:
                    cnt[tn]["own_box"] += 1
                    cnt[tn]["foul_lines"] += 1
        for team, v in cnt.items():
            rows.append(dict(fs_id=fs_id, team=team, **v))
    df = pd.DataFrame(rows)
    df["located"] = df[["att_half", "def_half", "wing", "own_box"]].sum(axis=1)
    df = df.sort_values("located").drop_duplicates(["fs_id", "team"], keep="last")  # same match listed twice by ESPN: keep the fuller log
    df.to_csv(os.path.join(OUT, "espn_fouls.csv"), index=False, encoding="utf-8-sig")
    print("unmatched ESPN matches:", miss, "| team-matches:", len(df))
    df["season"] = df.fs_id.map(fs.set_index("fs_id").season)
    g = df.groupby("season")[["foul_lines", "located", "att_half", "def_half", "wing", "own_box"]].sum()
    g["located_share_of_foul_lines"] = g.located / g.foul_lines
    print(g.round(3).to_string())


if __name__ == "__main__":
    main()
