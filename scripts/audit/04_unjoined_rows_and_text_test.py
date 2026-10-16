import re, importlib.util
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
RAW, P = ROOT / 'data' / 'raw', ROOT / 'data' / 'processed'
pd.set_option('display.width', 250, 'display.max_colwidth', 120)
spec = importlib.util.spec_from_file_location('b3', ROOT / 'scripts' / '03_build_dataset.py'); b3 = importlib.util.module_from_spec(spec); spec.loader.exec_module(b3)
tm = pd.read_csv(P / 'team_match.csv', parse_dates=['kickoff'])
print(tm[tm.xg.isna() & ~tm.team.isin(['Huesca', 'Oviedo'])][['season', 'team', 'opponent', 'kickoff', 'xg', 'xg_fs']].to_string())
print(tm[tm.ppda_att.isna() & ~tm.team.isin(['Huesca', 'Oviedo']) & ~tm.opponent.isin(['Huesca', 'Oviedo'])][['season', 'team', 'opponent', 'kickoff']].to_string())
u = pd.read_csv(RAW / 'understat_team_matches.csv'); print(u[(u.season == '2026-27')].groupby('team').size().sort_values().head(4).to_dict())
a = pd.read_csv(P / 'audit_event_evidence.csv')
# strict: VAR lines in the window must mention goal / offside / disallow / ruled out / net, not just foul/handball
STRICT = re.compile(r'(?i)\bgoal\b|offside|disallow|ruled out|chalk|\bnet\b|celebrat')
n = bad = 0; ex = []
for r in a.itertuples():
    lc = [x for x in b3.parse_commentary(b3.read('df_lc', r.fs_id)) if x['minute'] and b3.minute_num(x['minute']) is not None and r.minute - 1 <= b3.minute_num(x['minute']) <= r.minute + 3]
    vl = [x for x in lc if x['icon'] == 'var' or re.search(r'(?i)\bVAR\b|video assistant|video review', x['text'])]
    if not vl: continue
    n += 1
    if not any(STRICT.search(x['text']) for x in vl):
        bad += 1; ex.append((r.fs_id, r.team, r.minute, ' || '.join(x['text'][:120] for x in vl[:2])))
print('\nstrict test: events with VAR lines', n, '| VAR lines do not mention goal/offside/disallow/ruled out/net:', bad)
for e in ex[:12]: print(e)
