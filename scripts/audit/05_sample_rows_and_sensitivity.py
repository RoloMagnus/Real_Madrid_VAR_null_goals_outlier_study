import pandas as pd, numpy as np
from pathlib import Path
from scipy import stats
R = str(Path(__file__).resolve().parents[2])
pd.set_option('display.width', 250, 'display.max_colwidth', 70)
d = pd.read_csv(R + r'\data\processed\disallowed_goals_enriched.csv')
a = pd.read_csv(R + r'\data\processed\audit_event_evidence.csv')
print('== what the PIPELINE holds for the 4 hand-built sample rows')
chk = [('2018-09-26', 'Sevilla', 'Real Madrid'), ('2018-10-20', 'Levante', 'Real Madrid'), ('2018-12-01', 'Valencia', 'Real Madrid'), ('2019-03-10', 'Valladolid', 'Real Madrid'), ('2019-03-16', 'Celta', 'Real Madrid')]
for dt, riv, team in chk:
    x = d[(d.date == dt) & (d.home.str.contains(riv) | d.away.str.contains(riv))]
    print(dt, riv, '->', 'NO incident at all' if x.empty else x[['team', 'player_full', 'minute', 'reason_fs']].to_dict('records'))
print('\n== strictest rule: keep only events with explicit VAR wording (tiers A and C)')
ok = a[a.tier.str[0].isin(['A', 'C'])]
n_rm = int((ok.team == 'Real Madrid').sum()); n_all = len(ok)
rr = (n_rm / 312) / ((n_all - n_rm) / 5924)
ci = stats.binomtest(n_rm, n_all, 312 / (312 + 5924)).proportion_ci(0.95); f = lambda p: (p / (1 - p)) * (5924 / 312)
print(f' events {n_all} (RM {n_rm}) -> rate ratio {rr:.2f} (95% CI {f(ci.low):.2f}-{f(ci.high):.2f}); current rule: 394 (RM 50) -> 2.76')
print('\n== user video links: one link per match, no link shared across matches?')
v = pd.read_excel(R + r'\RM_nullified_goals_breakdown_validated.xlsx', sheet_name='RM_var_null_goals_breakdown')
v['match'] = v.date.astype(str) + '|' + v.rival
print(' rows', len(v), '| matches', v.match.nunique(), '| distinct links', v.links.nunique(), '| links mapping to >1 match:', int((v.groupby('links').match.nunique() > 1).sum()), '| matches with >1 link:', int((v.groupby('match').links.nunique() > 1).sum()))
print(' manual_validation values:', v.manual_validation.value_counts().to_dict())
