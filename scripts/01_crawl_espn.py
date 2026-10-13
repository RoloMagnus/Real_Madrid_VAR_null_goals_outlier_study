"""Crawl every La Liga match (2018-19 .. 2026-27 to date) from ESPN's public API.

Outputs
  data/raw/espn_cache/summary_<id>.json  (cached match summaries)
  data/raw/espn_matches.csv              (one row per match)
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "raw", "espn_cache")
os.makedirs(CACHE, exist_ok=True)

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1"
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (research; VAR-analysis)"


def get_json(url, retries=4):
    for i in range(retries):
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return None


def season_of(date_utc):
    d = pd.Timestamp(date_utc).tz_localize(None)
    if pd.Timestamp("2020-06-01") <= d < pd.Timestamp("2020-08-20"):
        return "2019-20"  # COVID-delayed finish
    y = d.year if d.month >= 7 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def list_matches():
    """The scoreboard only accepts single days or whole calendar years."""
    rows = []
    for year in range(2018, 2027):
        d = get_json(f"{BASE}/scoreboard?dates={year}&limit=500")
        evs = d.get("events", []) if d else []
        print(year, len(evs), flush=True)
        for e in evs:
            if e["date"] < "2018-08-01":
                continue
            c = e["competitions"][0]
            home = next(t for t in c["competitors"] if t["homeAway"] == "home")
            away = next(t for t in c["competitors"] if t["homeAway"] == "away")
            rows.append(dict(
                season=season_of(e["date"]), event_id=e["id"], date_utc=e["date"],
                home=home["team"]["displayName"], away=away["team"]["displayName"],
                home_goals=home.get("score"), away_goals=away.get("score"),
                status=e["status"]["type"]["description"],
            ))
    return pd.DataFrame(rows).drop_duplicates("event_id")

def fetch_summary(eid):
    path = os.path.join(CACHE, f"summary_{eid}.json")
    if os.path.exists(path):
        return True
    d = get_json(f"{BASE}/summary?event={eid}")
    if not d:
        return False
    with open(path, "w", encoding="utf8") as f:
        json.dump(d, f)
    return True


if __name__ == "__main__":
    m = list_matches()
    m.to_csv(os.path.join(ROOT, "data", "raw", "espn_matches.csv"), index=False, encoding="utf-8-sig")
    print(m.groupby("season").size())
    ids = m.event_id.tolist()
    with ThreadPoolExecutor(12) as ex:
        res = list(ex.map(fetch_summary, ids))
    print("fetched ok:", sum(res), "failed:", len(res) - sum(res))

