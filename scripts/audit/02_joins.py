"""Audit part 2: joins (ESPN, fouls, Understat, Transfermarkt referees) with a safe name mapping."""
import importlib.util, json, re, unicodedata
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
RAW, P = ROOT / 'data' / 'raw', ROOT / 'data' / 'processed'
pd.set_option('display.width', 250, 'display.max_colwidth', 80)
fs = pd.read_csv(P / 'matches_ref.csv'); es = pd.read_csv(RAW / 'espn_matches.csv', dtype={'event_id': str}); es = es[es.status == 'Full Time'].copy()
kk = lambda s: re.sub(r'[^a-z]', '', ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c)).lower())
canon = sorted(set(fs.home) | set(fs.away)); ck = {kk(c): c for c in canon}
ALIAS = {'atleticomadrid': 'Atlético de Madrid', 'celtavigo': 'Celta de Vigo', 'deportivo': 'Deportivo La Coruña', 'alaves': 'Deportivo Alavés'}
def safe(n):
    k = kk(n)
    if k in ALIAS: return ALIAS[k]
    if k in ck: return ck[k]
    c = [v for kc, v in ck.items() if k in kc or kc in k]
    return c[0] if len(c) == 1 else None          # ambiguous -> unmapped, never guessed
es['h'], es['a'] = es.home.map(safe), es.away.map(safe)
print('ESPN names unmapped:', es[es.h.isna() | es.a.isna()][['home', 'away']].drop_duplicates().head().to_string())
es['k'] = pd.to_datetime(es.date_utc).dt.tz_localize(None).dt.floor('h'); fs['k'] = pd.to_datetime(fs.date_utc).dt.floor('h')

print('\n=== A. ESPN join used by 05_enrich (kick-off hour + score), team names checked with the SAFE mapping')
j = fs.merge(es[['k', 'home_goals', 'away_goals', 'event_id', 'h', 'a']], on=['k', 'home_goals', 'away_goals'], how='left')
ncand = j.groupby('fs_id').event_id.transform(lambda s: s.notna().sum())
single = j[ncand == 1]
bad = single[(single.home != single.h) | (single.away != single.a)]
print(' matches with exactly 1 candidate:', single.fs_id.nunique(), '| mis-merged (team names disagree):', len(bad))
print(' matches with >1 candidate (dropped by keep=False -> ESPN fields blank):', j[ncand > 1].fs_id.nunique(), '| with 0 candidates:', j[ncand == 0].fs_id.nunique())
d = pd.read_csv(P / 'disallowed_goals_enriched.csv')
amb = set(j[ncand > 1].fs_id); none = set(j[ncand == 0].fs_id)
print(' of the 397 events: in ambiguous-dropped matches:', int(d.fs_id.isin(amb).sum()), '| in no-candidate matches:', int(d.fs_id.isin(none).sum()), '| espn_corroborated is null:', int(d.espn_corroborated.isna().sum()))
print(' Real Madrid events in ambiguous/none matches:', int(d[(d.team == 'Real Madrid') & (d.fs_id.isin(amb | none))].shape[0]))

print('\n=== B. Foul-zone join (09_fouls_espn.py): old names (substring fallback) vs safe mapping')
def old(n):
    k = kk(n)
    if k == 'atleticomadrid': return 'Atlético de Madrid'
    if k == 'celtavigo': return 'Celta de Vigo'
    for c in canon:
        if kk(c) == k: return c
    for c in canon:
        if k in kk(c) or kk(c) in k: return c
    return n
es['season'] = es.season if 'season' in es else None
key = fs.set_index(['season', 'home', 'away']).fs_id
rows = []
for r in es.itertuples():
    ho, ao = old(r.home), old(r.away)
    hs, as_ = safe(r.home), safe(r.away)
    k_old = key.get((r.season, ho, ao)) if hasattr(r, 'season') else None
    k_new = key.get((r.season, hs, as_)) if hasattr(r, 'season') else None
    rows.append((r.event_id, r.home, r.away, ho, ao, k_old, k_new))
x = pd.DataFrame(rows, columns=['event_id', 'espn_home', 'espn_away', 'old_h', 'old_a', 'fs_old', 'fs_new'])
print(' ESPN matches:', len(x), '| old-key resolves:', int(x.fs_old.notna().sum()), '| safe-key resolves:', int(x.fs_new.notna().sum()))
diff = x[(x.fs_old != x.fs_new) & (x.fs_old.notna() | x.fs_new.notna())]
print(' where the OLD key points to a different (or no) Flashscore match than the SAFE key:', len(diff)); print(diff.head(12).to_string())
dup = x[x.fs_old.notna()].fs_old.duplicated(keep=False)
print(' Flashscore matches that received data from 2 different ESPN matches under the old key:', int(x[x.fs_old.notna()][dup].fs_old.nunique()))
print(x[x.fs_old.notna()][dup].sort_values('fs_old').to_string())

print('\n=== C. Understat join check: Flashscore goals vs Understat scored/missed for the joined row')
tm = pd.read_csv(P / 'team_match.csv', parse_dates=['kickoff'])
u = pd.read_csv(RAW / 'understat_team_matches.csv'); u['date'] = pd.to_datetime(u.date)
UA = {'atleticomadrid': 'atleticodemadrid', 'barcelona': 'fcbarcelona', 'alaves': 'deportivoalaves', 'valladolid': 'realvalladolid', 'betis': 'realbetis', 'celtavigo': 'celtadevigo', 'athleticclub': 'athleticclub', 'leganes': 'leganes'}
ukey = lambda n: UA.get(kk(n), kk(n))
u['k'] = u.team.map(ukey); tm['k'] = tm.team.map(ukey); tm['date'] = tm.kickoff.dt.normalize()
out = []
for (s, kq), g in tm.groupby(['season', 'k']):
    uu = u[(u.season == s) & (u.k == kq)].sort_values('date')
    out.append(pd.merge_asof(g.sort_values('date'), uu[['date', 'scored', 'missed', 'xg']].rename(columns={'date': 'udate', 'xg': 'xg_u'}), left_on='date', right_on='udate', direction='nearest', tolerance=pd.Timedelta(days=2)))
m = pd.concat(out)
have = m.scored.notna()
print(' team-matches:', len(m), '| joined:', int(have.sum()), '| no Understat row:', int((~have).sum()))
bad = m[have & ((m.gf != m.scored) | (m.ga != m.missed))]
print(' joined rows whose goals DISAGREE with Understat (mis-merge signal):', len(bad)); print(bad[['season', 'team', 'opponent', 'kickoff', 'gf', 'ga', 'scored', 'missed']].head(10).to_string())
print(' unjoined by team:', m[~have].team.value_counts().head(6).to_dict(), '| by season:', m[~have].season.value_counts().to_dict())

print('\n=== D. Referee join: Transfermarkt full name vs Flashscore short name')
rt = pd.read_csv(P / 'referees_tm.csv'); mm = fs[['fs_id', 'referee_short']].merge(rt[['fs_id', 'referee_tm']], on='fs_id'); mm = mm[mm.referee_tm.notna() & mm.referee_short.notna()]
def agree(short, full):
    st = [t for t in re.findall(r'[a-z]+', ''.join(c for c in unicodedata.normalize('NFKD', short) if not unicodedata.combining(c)).lower()) if len(t) > 1]
    ft = set(re.findall(r'[a-z]+', ''.join(c for c in unicodedata.normalize('NFKD', full) if not unicodedata.combining(c)).lower()))
    return all(t in ft for t in st)
mm['ok'] = [agree(a, b) for a, b in zip(mm.referee_short, mm.referee_tm)]
print(' matches with both names:', len(mm), '| surname agrees:', int(mm.ok.sum()), '| disagree:', int((~mm.ok).sum()))
print(mm[~mm.ok].head(10).to_string())
