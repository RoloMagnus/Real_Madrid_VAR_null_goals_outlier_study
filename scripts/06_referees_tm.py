"""Referee full names from Transfermarkt match sheets (matches with a disallowed goal + all Real Madrid matches)."""
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "processed")
CACHE = os.path.join(ROOT, "data", "raw", "tm_cache")
os.makedirs(CACHE, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
     "Accept-Language": "en-US,en;q=0.9"}
S = requests.Session()
S.headers.update(H)


def k(n):
    n = "".join(c for c in unicodedata.normalize("NFKD", n) if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", n.lower())


def get(url, cache_name):
    p = os.path.join(CACHE, cache_name)
    if os.path.exists(p):
        return open(p, encoding="utf8").read()
    for _ in range(5):
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200:
                open(p, "w", encoding="utf8").write(r.text)
                return r.text
        except Exception:
            time.sleep(2)
    return ""


def matchday(args):
    season_id, md = args
    t = get(f"https://www.transfermarkt.com/laliga/spieltag/wettbewerb/ES1/saison_id/{season_id}/spieltag/{md}",
            f"md_{season_id}_{md}.html")
    rows = []
    for m in re.finditer(r'href="/spielbericht/index/spielbericht/(\d+)"><span class="matchresult finished">(\d+):(\d+)', t):
        before = re.findall(r'<a title="([^"]+)" href="/[^"]+/spielplan/verein/', t[max(0, m.start() - 2500):m.start()])
        after = re.findall(r'<a title="([^"]+)" href="/[^"]+/spielplan/verein/', t[m.end():m.end() + 2500])
        if before and after:
            rows.append(dict(season=f"{season_id}-{str(season_id + 1)[2:]}", tm_id=m.group(1), tm_home=before[-1],
                             tm_away=after[0], hg=int(m.group(2)), ag=int(m.group(3))))
    return rows


def sheet(tm_id):
    t = get(f"https://www.transfermarkt.com/spielbericht/index/spielbericht/{tm_id}", f"sheet_{tm_id}.html")
    m = re.search(r'Referee:</strong>\s*(?:<br[^>]*>)?\s*<a title="([^"]+)"', t)
    return tm_id, (m.group(1) if m else None)


def main():
    jobs = [(y, md) for y in range(2018, 2027) for md in range(1, 39)]
    with ThreadPoolExecutor(6) as ex:
        tm = [r for rows in ex.map(matchday, jobs) for r in rows]
    tm = pd.DataFrame(tm).drop_duplicates(["season", "tm_home", "tm_away"])
    print("TM matches indexed:", len(tm))

    ms = pd.read_csv(os.path.join(OUT, "matches.csv"))
    dis = pd.read_csv(os.path.join(OUT, "disallowed_goals_all.csv"))
    tm["hk"], tm["ak"] = tm.tm_home.map(k), tm.tm_away.map(k)

    def find(row):
        ali = {"athleticclub": "athleticbilbao"}
        hk, ak = ali.get(k(row.home), k(row.home)), ali.get(k(row.away), k(row.away))
        c = tm[(tm.season == row.season) & tm.hk.str.contains(hk, regex=False) & tm.ak.str.contains(ak, regex=False)]
        return c.tm_id.iloc[0] if len(c) == 1 else None

    ms["tm_id"] = [find(r) for r in ms.itertuples()]
    print("matched to TM:", ms.tm_id.notna().sum(), "of", len(ms))
    need = ms[ms.fs_id.isin(dis.fs_id) | (ms.home == "Real Madrid") | (ms.away == "Real Madrid")]
    ids = need.tm_id.dropna().unique().tolist()
    print("sheets to fetch:", len(ids))
    with ThreadPoolExecutor(6) as ex:
        refs = dict(ex.map(sheet, ids))
    ms["referee_tm"] = ms.tm_id.map(refs)
    ms[["fs_id", "tm_id", "referee_short", "referee_tm"]].to_csv(os.path.join(OUT, "referees_tm.csv"), index=False,
                                                                  encoding="utf-8-sig")
    print(ms.loc[ms.fs_id.isin(dis.fs_id), "referee_tm"].notna().mean())


if __name__ == "__main__":
    main()
