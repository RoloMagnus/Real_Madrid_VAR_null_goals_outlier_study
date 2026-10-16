"""Compare headline numbers of the repository analysis (before) with the isolated copy where the candidate fixes were applied (after).
Run 06_apply_fixes_in_isolated_copy.py first. The repository itself is not modified by either script."""
import pickle, os, numpy as np, pandas as pd
from pathlib import Path
pd.set_option('display.width', 250, 'display.max_columns', 30, 'display.max_colwidth', 60)
A = pickle.load(open(Path(__file__).resolve().parents[2] / 'data' / 'processed' / 'analysis.pkl', 'rb'))
B = pickle.load(open(os.path.join(os.environ['TEMP'], 'rm_audit_tree', 'data', 'processed', 'analysis.pkl'), 'rb'))
RM = 'Real Madrid'; A20 = 'All 20 teams per season'; T10 = 'Top-10 teams per season'
def cmp(name, a, b, fmt='{:.3f}'):
    print(f'{name:62s} {fmt.format(a):>10s} -> {fmt.format(b):>10s}')
for k in ('d',):
    va, vb = A['d'], B['d']
    print('VAR-confirmed events:', int(va.var_confirmed.sum()), '->', int(vb.var_confirmed.sum()), '| RM:', int((va.var_confirmed & (va.team == RM)).sum()), '->', int((vb.var_confirmed & (vb.team == RM)).sum()))
    ca, cb = va[va.var_confirmed].team.value_counts(), vb[vb.var_confirmed].team.value_counts()
    ch = pd.concat([ca, cb], axis=1, keys=['before', 'after']).fillna(0).astype(int); print('teams whose count changes:', ch[ch.before != ch.after].to_dict('index'))
    s = vb[(~vb.var_confirmed)][['date', 'home', 'away', 'team', 'minute', 'reason_fs']]; print('events NOT VAR-confirmed after the fix:'); print(s.to_string())
print()
ra = A['rate_tests']; rb = B['rate_tests']
for sc in (A20, T10):
    x, y = ra[(ra.scope.str.startswith(sc[:8])) & (ra.exposure == 'per match played')].iloc[0], rb[(rb.scope.str.startswith(sc[:8])) & (rb.exposure == 'per match played')].iloc[0]
    cmp(f'rate ratio per match [{sc[:14]}]', x.rate_ratio, y.rate_ratio, '{:.2f}'); cmp('   others events', x.others_nullified, y.others_nullified, '{:.0f}')
for key, lab in (('M0', 'raw'), ('M6', 'full volume model')):
    for sc in (A20, T10):
        x = A['glm'][(A['glm'].scope == sc) & A['glm'].model.str.startswith(key)].iloc[0]; y = B['glm'][(B['glm'].scope == sc) & B['glm'].model.str.startswith(key)].iloc[0]
        cmp(f'RM IRR {lab} [{sc[:10]}] (n {int(x.n_team_matches) if "n_team_matches" in x else "?"}->{int(y.n_team_matches) if "n_team_matches" in y else "?"})', x.rm_irr, y.rm_irr, '{:.3f}')
f = lambda O, sc: O['forecast'][(O['forecast'].scope == sc) & (O['forecast'].model_trained_on_other_teams == 'offsides + shots + xG')].iloc[0]
cmp('forecast expected (all, volume model)', f(A, A20).rm_expected, f(B, A20).rm_expected, '{:.1f}'); cmp('   interval low', f(A, A20).expected_p2_5, f(B, A20).expected_p2_5, '{:.0f}'); cmp('   interval high', f(A, A20).expected_p97_5, f(B, A20).expected_p97_5, '{:.0f}')
for nm, k in (('PPDA full', 'ppda_glm'), ('Discipline full', 'disc_glm')):
    for sc in (A20, T10):
        x = A[k][A[k].scope == sc].iloc[-1 if k == 'disc_glm' else 3]; y = B[k][B[k].scope == sc].iloc[-1 if k == 'disc_glm' else 3]
        cmp(f'{nm} RM IRR [{sc[:10]}] n {int(x.n_team_matches)}->{int(y.n_team_matches)}', x.rm_irr, y.rm_irr, '{:.3f}')
for k in ('ppda_glm', 'disc_glm'):
    x = A[k][A[k].scope == A20].iloc[0]; y = B[k][B[k].scope == A20].iloc[0]; cmp(f'{k} reference IRR (all)', x.rm_irr, y.rm_irr, '{:.3f}')
sa, sb = A['symmetry'], B['symmetry']
for i, lab in enumerate(('offsides', 'shots', 'xG', 'goal opps')): cmp(f'symmetry p [{lab}]', sa.iloc[i].p_value_rm_obs_or_more, sb.iloc[i].p_value_rm_obs_or_more, '{:.3f}'); 
cmp('opponents spared: ratio obs/exp (per match)', A['fav'].iloc[0].ratio_obs_over_exp, B['fav'].iloc[0].ratio_obs_over_exp, '{:.2f}'); cmp('   p', A['fav'].iloc[0].p_value_fewer_than_expected, B['fav'].iloc[0].p_value_fewer_than_expected, '{:.3f}')
cmp('referee heterogeneity p', A['ref_meta'].p_value.iloc[0], B['ref_meta'].p_value.iloc[0], '{:.3f}')
oa = A['onf_inter'][(A['onf_inter'].scope == A20) & A['onf_inter'].model.str.startswith('Controlled') & A['onf_inter'].term.str.startswith('Extra')].iloc[0]
ob = B['onf_inter'][(B['onf_inter'].scope == A20) & B['onf_inter'].model.str.startswith('Controlled') & B['onf_inter'].term.str.startswith('Extra')].iloc[0]
cmp('VAR-stage extra RM effect (IRR)', oa.irr, ob.irr, '{:.2f}'); cmp('   p', oa.p_value, ob.p_value, '{:.2f}')
la, lb = A['ledger'].set_index('team').loc[RM], B['ledger'].set_index('team').loc[RM]; cmp('net points ledger RM', la.net_points_from_nullified_goals, lb.net_points_from_nullified_goals, '{:.0f}')
ea, eb = A['espn_check'].set_index('team'), B['espn_check'].set_index('team')
print('\nESPN check, rows that changed:'); 
j = pd.concat([ea.espn_overturned_goals, eb.espn_overturned_goals], axis=1, keys=['before', 'after']).fillna(0); print(j[j.before != j.after].to_string())
print('\nxG missing %:', round(A['tm'].xg.isna().mean() * 100, 2), '->', round(B['tm'].xg.isna().mean() * 100, 2), '| ppda missing %:', round(A['tm'].ppda_att.isna().mean() * 100, 2), '->', round(B['tm'].ppda_att.isna().mean() * 100, 2))
