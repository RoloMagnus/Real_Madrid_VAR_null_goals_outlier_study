"""Independent audit of the 394 VAR-confirmed events for the three error types raised in a reader comment:
 (1) wrong minute  (2) VAR review that never happened  (3) mismatched / merged matches.
Reads raw caches directly; does not reuse the pipeline's var_flag."""
import importlib.util, json, re, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW, P = ROOT / 'data' / 'raw', ROOT / 'data' / 'processed'
spec = importlib.util.spec_from_file_location('b3', ROOT / 'scripts' / '03_build_dataset.py'); b3 = importlib.util.module_from_spec(spec); spec.loader.exec_module(b3)
spec = importlib.util.spec_from_file_location('b5', ROOT / 'scripts' / '05_enrich.py'); b5 = importlib.util.module_from_spec(spec); spec.loader.exec_module(b5)

d = pd.read_csv(P / 'disallowed_goals_enriched.csv')
all_inc = pd.read_csv(P / 'disallowed_goals_all.csv')
print('incidents (all):', len(all_inc), '| enriched rows:', len(d), '| var_flag:', int(d.var_flag.sum()))

# ------------------------------------------------------------------ (3) match-merge audit
fs = pd.read_csv(P / 'matches.csv')
es = pd.read_csv(RAW / 'espn_matches.csv', dtype={'event_id': str})
es = es[es.status == 'Full Time'].copy()
canon = sorted(set(fs.home) | set(fs.away))
kk = lambda s: re.sub(r'[^a-z]', '', ''.join(c for c in __import__('unicodedata').normalize('NFKD', str(s)) if not __import__('unicodedata').combining(c)).lower())
def to_canon(n):
    k = kk(n)
    if k == 'atleticomadrid': return 'Atlético de Madrid'
    if k == 'celtavigo': return 'Celta de Vigo'
    for c in canon:
        if kk(c) == k: return c
    for c in canon:
        if k in kk(c) or kk(c) in k: return c
    return n
es['h'], es['a'] = es.home.map(to_canon), es.away.map(to_canon)
# (a) join exactly as the pipeline does (kick-off hour + score), then compare team names
es['k'] = pd.to_datetime(es.date_utc).dt.tz_localize(None).dt.floor('h')
fs['k'] = pd.to_datetime(fs.date_utc).dt.floor('h')
j = fs.merge(es[['k', 'home_goals', 'away_goals', 'event_id', 'h', 'a']], on=['k', 'home_goals', 'away_goals'], how='left', suffixes=('', '_e'))
cnt = j.groupby('fs_id').event_id.transform(lambda s: s.notna().sum())
single = j[cnt == 1]
name_ok = (single.home == single.h) & (single.away == single.a)
print('\n== (3) merge audit (pipeline key = kickoff hour + score)')
print(' fs matches:', len(fs), '| with exactly one ESPN candidate:', single.fs_id.nunique(), '| ambiguous (>1 cand., dropped by keep=False):', int((cnt > 1).groupby(j.fs_id).first().sum()),
      '| no candidate:', int((cnt == 0).groupby(j.fs_id).first().sum()))
print(' single-candidate joins whose team names DISAGREE (true mis-merges):', int((~name_ok).sum()))
if (~name_ok).sum():
    print(single[~name_ok][['season', 'date', 'home', 'away', 'h', 'a']].head(10).to_string())
# (b) the stricter key (season, home, away) used by the fouls script
# ------------------------------------------------------------------ evidence tiers from raw
def espn_events_for(fs_row):
    c = es[(es.k == fs_row.k) & (es.home_goals == fs_row.home_goals) & (es.away_goals == fs_row.away_goals) & (es.h == fs_row.home) & (es.a == fs_row.away)]
    return c.event_id.iloc[0] if len(c) == 1 else None
fsi = fs.set_index('fs_id')
emap = {r.fs_id: espn_events_for(r) for r in fs.itertuples()}
print('\n matched to ESPN WITH team-name check:', sum(v is not None for v in emap.values()), 'of', len(emap))

def parse_min(s):
    m = re.sub(r'[^0-9+]', '', str(s or '')); 
    return sum(int(x) for x in m.split('+') if x) if m else None
cache = {}
def espn_ev(eid):
    if eid is None: return []
    if eid in cache: return cache[eid]
    dd = json.load(open(RAW / 'espn_cache' / f'summary_{eid}.json', encoding='utf8')); out = []
    for c in dd.get('commentary') or []:
        t = c.get('text') or ''; ty = ((c.get('play') or {}).get('type') or {}).get('text') or ''
        mn = parse_min((c.get('time') or {}).get('displayValue'))
        if ty == 'Deleted After Review' and t.startswith('GOAL OVERTURNED'): out.append(('overturned', mn, t))
        elif ty.startswith('VAR') and 'No Goal' in t: out.append(('no_goal', mn, t))
        elif 'Video Review' in t: out.append(('review_delay', mn, t))
    cache[eid] = out; return out

lc_cache = {}
def fs_lc(fid):
    if fid not in lc_cache:
        t = open(RAW / 'fs_cache' / f'df_lc_{fid}.txt', encoding='utf8').read(); rows = []
        for rec in t.split('~')[1:]:
            f, _ = b3.fields(rec)
            if 'MD' in f: rows.append((b3.minute_num(f.get('MB')), f.get('MC'), f['MD']))
        lc_cache[fid] = rows
    return lc_cache[fid]

rows = []
for r in d.itertuples():
    mn = r.minute_num
    lc = [x for x in fs_lc(r.fs_id) if x[0] is not None and mn - 1 <= x[0] <= mn + 3]
    icon_var = any(x[1] == 'var' for x in lc)
    word_var = any(re.search(r'\bVAR\b|video assistant|video review', x[2], re.I) for x in lc) or bool(re.search(r'\bVAR\b|video assistant', str(r.fs_text), re.I))
    disallow_only = any(re.search(r'disallow', x[2], re.I) for x in lc)
    ev = [e for e in espn_ev(emap.get(r.fs_id)) if e[1] is not None and abs(e[1] - mn) <= 3]
    explicit = any(e[0] in ('overturned', 'no_goal') for e in ev)
    review = any(e[0] == 'review_delay' for e in ev)
    rows.append(dict(fs_id=r.fs_id, team=r.team, season=r.season, minute=mn, icon_var=icon_var, word_var=word_var, disallow_word=disallow_only,
                     espn_explicit=explicit, espn_review_delay=review, espn_matched=emap.get(r.fs_id) is not None,
                     espn_min=min((e[1] for e in ev if e[0] in ('overturned', 'no_goal')), default=np.nan), pipeline_var_flag=r.var_flag))
a = pd.DataFrame(rows)
a['tier'] = np.select([a.espn_explicit & (a.icon_var | a.word_var), a.espn_explicit, a.icon_var | a.word_var, a.espn_review_delay],
                      ['A: ESPN explicit VAR + Flashscore VAR wording', 'B: ESPN explicit VAR only', 'C: Flashscore VAR wording only', 'D: ESPN review delay only'],
                      'E: only the word "disallow" / nothing')
a.to_csv(ROOT / 'data' / 'processed' / 'audit_event_evidence.csv', index=False, encoding='utf-8-sig')
print('\n== (2) evidence behind the 397 incidents (independent of pipeline var_flag)')
print(a.tier.value_counts().sort_index().to_string())
print(' pipeline var_flag among tier E:', a[a.tier.str.startswith('E')].pipeline_var_flag.value_counts().to_dict())
print(' ESPN-matched share:', round(a.espn_matched.mean(), 3))
print('\n Real Madrid (50 + any) by tier:'); print(a[a.team == 'Real Madrid'].tier.value_counts().sort_index().to_string())
print('\n tier E / D events:')
x = a[a.tier.str[0].isin(['D', 'E'])].merge(d[['fs_id', 'minute', 'minute_num', 'date', 'home', 'away', 'player_full', 'reason_fs', 'fs_text']], left_on=['fs_id', 'minute'], right_on=['fs_id', 'minute_num'], how='left')
pd.set_option('display.width', 250, 'display.max_colwidth', 90)
print(x[['tier', 'season', 'date', 'home', 'away', 'team', 'player_full', 'minute_x', 'reason_fs', 'pipeline_var_flag']].to_string())
# ------------------------------------------------------------------ (1) minute audit
print('\n== (1) minute audit: Flashscore incident minute minus ESPN explicit-VAR minute')
m = a[a.espn_explicit].copy(); m['diff'] = m.minute - m.espn_min
print(' events with ESPN explicit minute:', len(m)); print(m['diff'].value_counts().sort_index().to_string())
print(' |diff|<=1: %.1f%%  |diff|<=2: %.1f%%  max |diff|: %d' % (100 * (m['diff'].abs() <= 1).mean(), 100 * (m['diff'].abs() <= 2).mean(), m['diff'].abs().max()))
