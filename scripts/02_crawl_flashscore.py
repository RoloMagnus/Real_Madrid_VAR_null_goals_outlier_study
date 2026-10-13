"""Crawl La Liga 2018-19 .. 2026-27 (to 12-Oct-2026) from Flashscore feeds.

For every match: incidents (df_sui_1), stats (df_st_1), match info/referee (df_sur_1).
For matches with any VAR-type incident: live commentary (df_lc_1) for context text.
Outputs raw text in data/raw/fs_cache/ and the match index data/raw/fs_matches.csv.
"""
import datetime
import os
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "raw", "fs_cache")
os.makedirs(CACHE, exist_ok=True)

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36",
     "x-fsign": "SW9D1eZo", "Referer": "https://www.flashscore.com/"}
B = "https://global.flashscore.ninja/2/x/feed/"
S = requests.Session()
S.headers.update(H)

# season label -> (results page slug, season code used by the 'show more' feed)
SEASONS = {
    "2018-19": ("laliga-2018-2019", 169),
    "2019-20": ("laliga-2019-2020", 170),
    "2020-21": ("laliga-2020-2021", 171),
    "2021-22": ("laliga-2021-2022", 172),
    "2022-23": ("laliga-2022-2023", 176),
    "2023-24": ("laliga-2023-2024", 183),
    "2024-25": ("laliga-2024-2025", 184),
    "2025-26": ("laliga-2025-2026", 187),
    "2026-27": ("laliga", None),
}


def get(url, tries=4):
    for _ in range(tries):
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
    return None


def parse_matches(txt, season):
    rows = []
    for rec in txt.split("~AA÷")[1:]:
        f = dict(x.split("÷", 1) for x in ("AA÷" + rec).split("¬") if "÷" in x)
        if "AE" not in f or "AD" not in f:
            continue
        rows.append(dict(
            season=season, fs_id=f["AA"],
            date_utc=datetime.datetime.fromtimestamp(int(f["AD"]), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M"),
            round=f.get("ER", ""), home=f["AE"], away=f["AF"],
            home_goals=f.get("AG"), away_goals=f.get("AH"),
        ))
    return rows


def list_matches():
    rows = []
    for season, (slug, code) in SEASONS.items():
        page = get(f"https://www.flashscore.com/football/spain/{slug}/results/")
        rows += parse_matches(page, season)  # whole page: results + fixtures feeds
        if code:
            for pg in range(1, 6):
                t = get(f"{B}tr_1_176_QVmLl54o_{code}_{pg}_-5_en_1")
                got = parse_matches(t, season) if t and len(t) > 5 else []
                if not got:
                    break
                rows += got
        n = sum(1 for r in rows if r["season"] == season)
        print(season, n, flush=True)
    df = pd.DataFrame(rows).drop_duplicates("fs_id")
    df = df[df.home_goals.notna() & (df.home_goals != "")]  # drop unplayed fixtures
    return df


def fetch(feed, mid):
    path = os.path.join(CACHE, f"{feed}_{mid}.txt")
    if os.path.exists(path):
        return open(path, encoding="utf8").read()
    t = get(f"{B}{feed}_1_{mid}")
    if t is None:
        return None
    with open(path, "w", encoding="utf8") as fh:
        fh.write(t)
    return t


def work(mid):
    sui = fetch("df_sui", mid)
    fetch("df_st", mid)
    fetch("df_sur", mid)
    if sui and ("IKX÷" in sui or "VAR" in sui):
        fetch("df_lc", mid)
    return sui is not None


if __name__ == "__main__":
    df = list_matches()
    df.to_csv(os.path.join(ROOT, "data", "raw", "fs_matches.csv"), index=False, encoding="utf-8-sig")
    ids = df.fs_id.tolist()
    with ThreadPoolExecutor(12) as ex:
        ok = list(ex.map(work, ids))
    print("matches", len(ids), "ok", sum(ok))
