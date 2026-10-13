"""Goals ruled out ON THE PITCH (assistant-referee flag / whistle) with no VAR review - all teams.

Flashscore commentary phrase: 'The assistant referee raises his flag and the referee blows his whistle.
<Player> (<Team>) puts the ball into the net, but he is flagged for offside.'
Downloads df_lc (commentary) for every match not yet cached, then parses.
Output: data/processed/onfield_disallowed_all.csv
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "raw", "fs_cache")
OUT = os.path.join(ROOT, "data", "processed")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36", "x-fsign": "SW9D1eZo",
     "Referer": "https://www.flashscore.com/"}
B = "https://global.flashscore.ninja/2/x/feed/"
S = requests.Session()
S.headers.update(H)


def fetch(mid):
    p = os.path.join(CACHE, f"df_lc_{mid}.txt")
    if os.path.exists(p):
        return True
    for _ in range(4):
        try:
            r = S.get(f"{B}df_lc_1_{mid}", timeout=40)
            if r.status_code == 200:
                open(p, "w", encoding="utf8").write(r.text)
                return True
        except Exception:
            pass
    return False


# primary phrase + looser variants (net + 'but' + flagged/offside/whistle) so we can see what else exists
STRICT = re.compile(r"(?P<player>[^.]+?) \((?P<team>[^)]+)\) puts the ball into the net, but (?:he|she) is flagged for offside", re.I)
LOOSE = re.compile(r"(?i)(into the net|in the net|ball is in the net|scores?).{0,60}(flag|offside|whistle|disallow|ruled out|not count|won.t count)")


def main():
    m = pd.read_csv(os.path.join(OUT, "matches.csv"))
    with ThreadPoolExecutor(12) as ex:
        ok = list(ex.map(fetch, m.fs_id.tolist()))
    print("commentary available:", sum(ok), "of", len(ok))
    rows, loose = [], []
    for r in m.itertuples():
        p = os.path.join(CACHE, f"df_lc_{r.fs_id}.txt")
        if not os.path.exists(p):
            continue
        for rec in open(p, encoding="utf8").read().split("~")[1:]:
            d = dict(x.split("÷", 1) for x in rec.split("¬") if "÷" in x)
            t = d.get("MD", "")
            if not t:
                continue
            s = STRICT.search(t)
            if s and "VAR" not in t:
                rows.append(dict(fs_id=r.fs_id, season=r.season, date=r.date, home=r.home, away=r.away, minute=d.get("MB"),
                                 player=s.group("player").split(". ")[-1].strip(), team_fs=s.group("team"), text=t[:300]))
            elif LOOSE.search(t) and "VAR" not in t:
                loose.append(dict(fs_id=r.fs_id, minute=d.get("MB"), text=t[:260]))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "onfield_disallowed_all.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(loose).to_csv(os.path.join(OUT, "onfield_disallowed_loose_candidates.csv"), index=False, encoding="utf-8-sig")
    print("strict pattern events:", len(df), "| loose candidates (non-VAR):", len(loose))


if __name__ == "__main__":
    main()
