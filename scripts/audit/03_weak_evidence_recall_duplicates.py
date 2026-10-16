import re, json, importlib.util, unicodedata
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
RAW, P = ROOT / 'data' / 'raw', ROOT / 'data' / 'processed'
pd.set_option('display.width', 260, 'display.max_colwidth', 150, 'display.max_columns', 30)
spec = importlib.util.spec_from_file_location('b3', ROOT / 'scripts' / '03_build_dataset.py'); b3 = importlib.util.module_from_spec(spec); spec.loader.exec_module(b3)
fs = pd.read_csv(P / 'matches_ref.csv'); d = pd.read_csv(P / 'disallowed_goals_enriched.csv'); a = pd.read_csv(P / 'audit_event_evidence.csv')
u = pd.read_csv(RAW / 'understat_team_matches.csv')
print('Understat names containing huesca/oviedo/rayo/athletic:', sorted({t for t in u.team if re.search('(?i)huesca|oviedo|rayo|athletic', t)}))
print('Flashscore names:', sorted({t for t in set(fs.home) | set(fs.away) if re.search('(?i)huesca|oviedo|rayo|athletic', t)}))
print('\nreferee disagreement match:'); print(fs[fs.fs_id == 'GGiPsLP1'][['season', 'date', 'home', 'away', 'referee_short', 'referee']].to_string())
print(' in events?', 'GGiPsLP1' in set(d.fs_id), '| RM match?', bool(((fs.fs_id == 'GGiPsLP1') & ((fs.home == 'Real Madrid') | (fs.away == 'Real Madrid'))).any()))

# ---- tier D/E detail with the commentary that exists
print('\n=== events with weak evidence (tiers D/E): what the commentary says and whether the pipeline counted them')
vc = pd.read_csv(P / 'disallowed_goals_enriched.csv')
import pickle
O = pickle.load(open(P / 'analysis.pkl', 'rb')); dv = O['d'][['fs_id', 'minute_num', 'team', 'var_confirmed', 'var_flag']]
w = a[a.tier.str[0].isin(['D', 'E'])].merge(dv, left_on=['fs_id', 'minute', 'team'], right_on=['fs_id', 'minute_num', 'team'], how='left', suffixes=('', '_p'))
for r in w.itertuples():
    mt = fs[fs.fs_id == r.fs_id].iloc[0]
    lc = [x for x in b3.parse_commentary(b3.read('df_lc', r.fs_id)) if x['minute'] and b3.minute_num(x['minute']) is not None and r.minute - 3 <= b3.minute_num(x['minute']) <= r.minute + 3]
    print(f'\n[{r.tier[:1]}] {mt.date} {mt.home}-{mt.away} {r.team} {r.minute}\' | pipeline var_confirmed={r.var_confirmed}')
    for x in lc[:5]: print('    ', x['minute'], x['icon'], '|', x['text'][:150])

# ---- cross-incident contamination: do the VAR lines in the window concern the goal?
print('\n=== do the VAR lines in the window concern a GOAL (not a penalty / card)?')
GOAL = re.compile(r'(?i)goal|offside|disallow|net|celebrat|ruled out|chalk|handball|foul')
PEN = re.compile(r'(?i)penalty|red card|sent off|booked|yellow')
rows = []
for r in a.itertuples():
    lc = [x for x in b3.parse_commentary(b3.read('df_lc', r.fs_id)) if x['minute'] and b3.minute_num(x['minute']) is not None and r.minute - 1 <= b3.minute_num(x['minute']) <= r.minute + 3]
    vl = [x for x in lc if x['icon'] == 'var' or re.search(r'(?i)\bVAR\b|video assistant|video review', x['text'])]
    if not vl: continue
    goalish = any(GOAL.search(x['text']) for x in vl)
    penonly = (not goalish) and any(PEN.search(x['text']) for x in vl)
    rows.append((r.fs_id, r.team, r.minute, goalish, penonly, ' || '.join(x['text'][:110] for x in vl[:3])))
c = pd.DataFrame(rows, columns=['fs_id', 'team', 'minute', 'goalish', 'penonly', 'text'])
print(' events with VAR commentary lines:', len(c), '| mention goal/offside/foul/handball:', int(c.goalish.sum()), '| penalty/card only:', int(c.penonly.sum()), '| other:', int((~c.goalish & ~c.penonly).sum()))
print(c[~c.goalish].to_string())

# ---- duplicates inside the 397
print('\n=== possible double counting: same match + team within 2 minutes')
x = d.sort_values(['fs_id', 'team', 'minute_num']); x['gap'] = x.groupby(['fs_id', 'team']).minute_num.diff()
print(x[x.gap <= 2][['date', 'home', 'away', 'team', 'player_full', 'minute', 'reason_fs', 'gap']].to_string())

# ---- recall vs ESPN explicit overturned events (2022-23+) by team
print('\n=== recall: ESPN "GOAL OVERTURNED BY VAR" events not present in our incident list')
es = pd.read_csv(RAW / 'espn_matches.csv', dtype={'event_id': str}); es = es[es.status == 'Full Time']
inc = pd.read_csv(P / 'disallowed_goals_all.csv'); inc['mn'] = inc.minute.map(b3.minute_num)
miss, tot = [], 0
for r in fs.itertuples():
    pass
fs['k'] = pd.to_datetime(fs.date_utc).dt.floor('h'); es['k'] = pd.to_datetime(es.date_utc).dt.tz_localize(None).dt.floor('h')
mp = fs.merge(es[['k', 'home_goals', 'away_goals', 'event_id']], on=['k', 'home_goals', 'away_goals'], how='left')
mp = mp[mp.groupby('fs_id').event_id.transform(lambda s: s.notna().sum()) == 1]
for r in mp.itertuples():
    if r.season < '2022-23': continue
    j = json.load(open(RAW / 'espn_cache' / f'summary_{r.event_id}.json', encoding='utf8'))
    for cm in j.get('commentary') or []:
        t = cm.get('text') or ''
        if ((cm.get('play') or {}).get('type') or {}).get('text') == 'Deleted After Review' and t.startswith('GOAL OVERTURNED'):
            m = re.search(r'VAR: (.+?) \((.+?)\) scores', t); mn = b3.minute_num((cm.get('time') or {}).get('displayValue'))
            tot += 1
            have = inc[(inc.fs_id == r.fs_id) & ((inc.mn - mn).abs() <= 4)]
            if have.empty: miss.append((r.season, r.date, r.home, r.away, m.group(1) if m else '?', m.group(2) if m else '?', mn))
print(' ESPN overturned events (2022-23 onwards, matches with a unique ESPN match):', tot, '| missing from our 397:', len(miss))
print(pd.DataFrame(miss, columns=['season', 'date', 'home', 'away', 'player', 'team', 'minute']).to_string())
