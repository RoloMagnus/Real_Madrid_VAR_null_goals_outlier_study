"""Fetch team-season xG / xGA / shots context from Understat (League data, La Liga)."""
import json
import os

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = {"User-Agent": "Mozilla/5.0 Chrome/120", "X-Requested-With": "XMLHttpRequest",
     "Referer": "https://understat.com/league/La_liga/2018"}

rows = []
for y in range(2018, 2027):
    r = requests.get(f"https://understat.com/getLeagueData/La_liga/{y}", headers=H, timeout=60)
    if r.status_code != 200:
        print(y, "HTTP", r.status_code)
        continue
    d = r.json()
    season = f"{y}-{str(y + 1)[2:]}"
    n = 0
    for tid, t in d["teams"].items():
        for h in t["history"]:
            rows.append(dict(season=season, team=t["title"], date=h["date"][:10], venue=h["h_a"],
                             xg=h["xG"], xga=h["xGA"], npxg=h["npxG"], scored=h["scored"], missed=h["missed"],
                             deep=h["deep"], ppda_att=h["ppda"]["att"], ppda_def=h["ppda"]["def"]))
            n += 1
    print(season, len(d["teams"]), "teams", n, "team-matches")
df = pd.DataFrame(rows)
df.to_csv(os.path.join(ROOT, "data", "raw", "understat_team_matches.csv"), index=False, encoding="utf-8-sig")
print(df.groupby("season").size())
