"""Statistical / EDA engine.  Reads data/processed/*, writes data/processed/analysis.pkl (dict of DataFrames)."""
import json
import os
import pickle
import re
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "data", "processed")
RAW = os.path.join(ROOT, "data", "raw")
RM = "Real Madrid"
rng = np.random.default_rng(2026)
OUT = {}


def load():
    tm = pd.read_csv(os.path.join(P, "team_match.csv"), parse_dates=["kickoff"])
    d = pd.read_csv(os.path.join(P, "disallowed_goals_enriched.csv"), parse_dates=["kickoff"])
    mt = pd.read_csv(os.path.join(P, "matches_ref.csv"))
    ft = pd.read_csv(os.path.join(P, "final_tables.csv"))
    # VAR-attributed = VAR wording in Flashscore text/commentary OR ESPN explicit VAR no-goal event
    txt = d.fs_text.fillna("") + " " + d.var_commentary.fillna("")
    d["var_confirmed"] = d.var_flag | txt.str.contains(r"VAR|video assistant", case=False) | (d.espn_corroborated == True)
    return tm, d, mt, ft


def add_d_to_tm(tm, d):
    dd = d[d.var_confirmed].groupby(["fs_id", "team"]).size().rename("dis")
    tm = tm.merge(dd, left_on=["fs_id", "team"], right_index=True, how="left")
    tm["dis"] = tm.dis.fillna(0).astype(int)
    by = d[d.var_confirmed].groupby(["fs_id", "team", "reason_fs"]).size().unstack(fill_value=0)
    by.columns = [f"dis_{c.replace(' ', '_')}" for c in by.columns]
    tm = tm.merge(by, left_on=["fs_id", "team"], right_index=True, how="left")
    for c in by.columns:
        tm[c] = tm[c].fillna(0).astype(int)
    fo = pd.read_csv(os.path.join(P, "espn_fouls.csv")).rename(
        columns={"att_half": "fouls_att_half", "def_half": "fouls_def_half", "wing": "fouls_wing", "own_box": "fouls_own_box",
                 "located": "fouls_located", "foul_lines": "fouls_espn"})
    tm = tm.merge(fo, on=["fs_id", "team"], how="left")
    tm["fouls_att_share"] = tm.fouls_att_half / tm.fouls_located.replace(0, np.nan)
    onf = pd.read_csv(os.path.join(P, "onfield_disallowed_events.csv"))
    oc = onf.groupby(["fs_id", "team"]).size().rename("onf")
    tm = tm.merge(oc, left_on=["fs_id", "team"], right_index=True, how="left")
    tm["onf"] = tm.onf.fillna(0).astype(int)
    tm["any_disallowed"] = tm.dis + tm.onf
    for c in ("shots", "sot", "offsides", "corners", "xg", "possession", "blocked", "fouls", "yellow", "red"):
        tm[c] = pd.to_numeric(tm[c], errors="coerce")
    return tm


# ---------------------------------------------------------------- cross-source validation of match stats
def validate_stats(tm):
    """Flashscore shots/SOT/offsides/corners vs ESPN box scores (independent provider), and Flashscore xG vs Understat."""
    mt = pd.read_csv(os.path.join(P, "matches.csv"))
    es = pd.read_csv(os.path.join(RAW, "espn_matches.csv"), dtype={"event_id": str})
    es = es[es.status == "Full Time"].copy()
    rows = []
    for r in es.itertuples():
        d = json.load(open(os.path.join(RAW, "espn_cache", f"summary_{r.event_id}.json"), encoding="utf8"))
        teams = (d.get("boxscore") or {}).get("teams") or []
        rec = {"k": pd.Timestamp(r.date_utc).tz_localize(None).floor("h"), "hg": int(r.home_goals), "ag": int(r.away_goals)}
        for t in teams:
            ha = t.get("homeAway")
            for s in t.get("statistics", []):
                if s["name"] in ("totalShots", "shotsOnTarget", "offsides", "wonCorners", "foulsCommitted"):
                    try:
                        rec[f"{ha}_{s['name']}"] = float(s["displayValue"])
                    except Exception:
                        pass
        rows.append(rec)
    e = pd.DataFrame(rows)
    mt["k"] = pd.to_datetime(mt.date_utc).dt.floor("h")
    j = mt.merge(e, left_on=["k", "home_goals", "away_goals"], right_on=["k", "hg", "ag"], how="inner")
    j = j.drop_duplicates("fs_id", keep=False)
    h = tm[tm.venue == "H"].set_index("fs_id")
    a = tm[tm.venue == "A"].set_index("fs_id")
    out = []
    for name, fs_col, es_col in (("Total shots", "shots", "totalShots"), ("Shots on target", "sot", "shotsOnTarget"),
                                 ("Offsides", "offsides", "offsides"), ("Corners", "corners", "wonCorners"),
                                 ("Fouls", "fouls", "foulsCommitted")):
        x = np.r_[j.fs_id.map(h[fs_col]).values, j.fs_id.map(a[fs_col]).values]
        y = np.r_[j[f"home_{es_col}"].values, j[f"away_{es_col}"].values]
        m = ~(np.isnan(x.astype(float)) | np.isnan(y.astype(float)))
        x, y = x[m].astype(float), y[m].astype(float)
        out.append(dict(metric=name, team_matches_compared=len(x), pearson_r=np.corrcoef(x, y)[0, 1],
                        exact_match_pct=100 * np.mean(x == y), within_1_pct=100 * np.mean(np.abs(x - y) <= 1),
                        mean_flashscore=x.mean(), mean_espn=y.mean(), mean_abs_diff=np.mean(np.abs(x - y))))
    v = pd.DataFrame(out)
    # xG: Flashscore (where published) vs Understat
    u = pd.read_csv(os.path.join(RAW, "understat_team_matches.csv"))
    both = tm.dropna(subset=["xg_fs", "xg"])
    v2 = pd.DataFrame([dict(metric="xG (Flashscore vs Understat)", team_matches_compared=len(both),
                            pearson_r=np.corrcoef(both.xg_fs, both.xg)[0, 1], exact_match_pct=np.nan,
                            within_1_pct=100 * np.mean(np.abs(both.xg_fs - both.xg) <= 0.25),
                            mean_flashscore=both.xg_fs.mean(), mean_espn=both.xg.mean(),
                            mean_abs_diff=np.mean(np.abs(both.xg_fs - both.xg)))])
    v2 = v2.rename(columns={})
    return pd.concat([v, v2], ignore_index=True)


# ---------------------------------------------------------------- team-season table
def team_season(tm):
    g = tm.groupby(["season", "team"])
    ts = g.agg(matches=("fs_id", "size"), final_pos=("final_pos", "first"), top10=("top10", "first"),
               goals=("gf", "sum"), goals_against=("ga", "sum"), shots=("shots", "sum"), sot=("sot", "sum"),
               xg=("xg", "sum"), offsides=("offsides", "sum"), corners=("corners", "sum"),
               possession=("possession", "mean"), dis=("dis", "sum"), pts=("pts", "sum"),
               ppda_att_pm=("ppda_att", "mean"), ppda_def_pm=("ppda_def", "mean"),
               opp_ppda_att_pm=("opp_ppda_att", "mean"), opp_ppda_def_pm=("opp_ppda_def", "mean"),
               fouls_pm=("fouls", "mean"), fouls_att_pm=("fouls_att_half", "mean"), fouls_def_pm=("fouls_def_half", "mean"),
               yellow_pm=("yellow", "mean"), red_pm=("red", "mean"),
               fouls_att_total=("fouls_att_half", "sum"), fouls_located_total=("fouls_located", "sum")).reset_index()
    ts["fouls_att_share_pm"] = ts.fouls_att_total / ts.fouls_located_total.replace(0, np.nan)
    ts["ppda_pm"] = ts.ppda_att_pm / ts.ppda_def_pm
    ts["opp_ppda_pm"] = ts.opp_ppda_att_pm / ts.opp_ppda_def_pm
    for c in ("shots", "sot", "xg", "offsides", "corners", "goals", "dis"):
        ts[f"{c}_pm"] = ts[c] / ts.matches
    ts["dis_per_100_goal_events"] = 100 * ts.dis / (ts.goals + ts.dis)
    ts["dis_per_100_shots"] = 100 * ts.dis / ts.shots
    ts["dis_per_100_offsides"] = 100 * ts.dis / ts.offsides
    ts["partial_season"] = ts.season == "2026-27"
    return ts


def corr_row(x, y, label_x, label_y, scope, n_boot=2000):
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = np.asarray(x)[m], np.asarray(y)[m]
    r, pr = stats.pearsonr(x, y)
    rho, ps = stats.spearmanr(x, y)
    tau, pk = stats.kendalltau(x, y)
    idx = rng.integers(0, len(x), (n_boot, len(x)))
    bs = [np.corrcoef(x[i], y[i])[0, 1] for i in idx]
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    return dict(scope=scope, x=label_x, y=label_y, n=len(x), pearson_r=r, pearson_p=pr, pearson_ci_low=lo,
                pearson_ci_high=hi, spearman_rho=rho, spearman_p=ps, kendall_tau=tau, kendall_p=pk)


def correlations(ts):
    rows = []
    top = ts[ts.top10]
    full = top[~top.partial_season]
    pairs = [("shots", "Shots (chances created)"), ("sot", "Shots on target"), ("xg", "xG"),
             ("offsides", "Offsides (attacking positions)"), ("corners", "Corners"), ("goals", "Goals scored")]
    for col, lab in pairs:
        rows.append(corr_row(full.dis.values.astype(float), full[col].values.astype(float), "VAR-nullified goals", lab,
                             "Top-10 team-seasons, 8 full seasons (counts)"))
        rows.append(corr_row(top.dis_pm.values, top[f"{col}_pm"].values, "VAR-nullified goals / match", lab + " / match",
                             "Top-10 team-seasons, 9 seasons incl. 2026-27 (per match)"))
        nrm = full[full.team != RM]
        rows.append(corr_row(nrm.dis.values.astype(float), nrm[col].values.astype(float), "VAR-nullified goals", lab,
                             "Top-10 team-seasons, 8 full seasons, excluding Real Madrid"))
    agg = top.groupby("team").agg(seasons=("season", "size"), matches=("matches", "sum"), dis=("dis", "sum"),
                                  shots=("shots", "sum"), sot=("sot", "sum"), xg=("xg", "sum"),
                                  offsides=("offsides", "sum"), corners=("corners", "sum"), goals=("goals", "sum")).reset_index()
    for c in ("dis", "shots", "sot", "xg", "offsides", "corners", "goals"):
        agg[f"{c}_pm"] = agg[c] / agg.matches
    for col, lab in pairs:
        rows.append(corr_row(agg.dis_pm.values, agg[f"{col}_pm"].values, "VAR-nullified goals / match", lab + " / match",
                             "Top-10 teams aggregated over 2018-2026 (n = teams)"))
    # PPDA components (per-match means): own pressing and the pressing faced from opponents
    ppda_pairs = [("ppda_att_pm", "PPDA att: opponent passes in pressing zone / match (own pressing)"),
                  ("ppda_def_pm", "PPDA def: own defensive actions in pressing zone / match"),
                  ("opp_ppda_att_pm", "Opp. PPDA att: own passes in opponent's pressing zone / match"),
                  ("opp_ppda_def_pm", "Opp. PPDA def: opponent defensive actions / match")]
    for col, lab in ppda_pairs:
        rows.append(corr_row(top.dis_pm.values, top[col].values, "VAR-nullified goals / match", lab,
                             "Top-10 team-seasons, 9 seasons incl. 2026-27 (per match)"))
        nrm = top[top.team != RM]
        rows.append(corr_row(nrm.dis_pm.values, nrm[col].values, "VAR-nullified goals / match", lab,
                             "Top-10 team-seasons, 9 seasons, excluding Real Madrid"))
    w = top.assign(**{c: top[c] * top.matches for c in ("ppda_att_pm", "ppda_def_pm", "opp_ppda_att_pm", "opp_ppda_def_pm")})
    wa = w.groupby("team")[["ppda_att_pm", "ppda_def_pm", "opp_ppda_att_pm", "opp_ppda_def_pm", "matches"]].sum()
    for c in ("ppda_att_pm", "ppda_def_pm", "opp_ppda_att_pm", "opp_ppda_def_pm"):
        agg[c] = agg.team.map(wa[c] / wa.matches)
    agg["ppda_pm"] = agg.ppda_att_pm / agg.ppda_def_pm
    agg["opp_ppda_pm"] = agg.opp_ppda_att_pm / agg.opp_ppda_def_pm
    for col, lab in ppda_pairs:
        rows.append(corr_row(agg.dis_pm.values, agg[col].values, "VAR-nullified goals / match", lab,
                             "Top-10 teams aggregated over 2018-2026 (n = teams)"))
    # discipline variables (per-match means)
    disc_pairs = [("fouls_pm", "Fouls committed / match"), ("fouls_att_pm", "Fouls committed in attacking half / match"),
                  ("fouls_def_pm", "Fouls committed in defensive half / match"), ("yellow_pm", "Yellow cards / match"),
                  ("red_pm", "Red cards / match"), ("fouls_att_share_pm", "Share of located fouls committed in attacking half")]
    for col, lab in disc_pairs:
        t_ = top.dropna(subset=[col])
        rows.append(corr_row(t_.dis_pm.values, t_[col].values, "VAR-nullified goals / match", lab,
                             "Top-10 team-seasons, 9 seasons incl. 2026-27 (per match)"))
        n_ = t_[t_.team != RM]
        rows.append(corr_row(n_.dis_pm.values, n_[col].values, "VAR-nullified goals / match", lab,
                             "Top-10 team-seasons, 9 seasons, excluding Real Madrid"))
    wd = top.dropna(subset=["fouls_pm"])
    ag2 = wd.groupby("team").apply(lambda g_: pd.Series({
        "fouls_pm": np.average(g_.fouls_pm, weights=g_.matches), "fouls_att_pm": np.average(g_.fouls_att_pm, weights=g_.matches),
        "fouls_def_pm": np.average(g_.fouls_def_pm, weights=g_.matches), "yellow_pm": np.average(g_.yellow_pm, weights=g_.matches),
        "red_pm": np.average(g_.red_pm, weights=g_.matches),
        "fouls_att_share_pm": g_.fouls_att_total.sum() / g_.fouls_located_total.sum()})).reset_index()
    agg = agg.merge(ag2, on="team", how="left")
    for col, lab in disc_pairs:
        rows.append(corr_row(agg.dis_pm.values, agg[col].values, "VAR-nullified goals / match", lab,
                             "Top-10 teams aggregated over 2018-2026 (n = teams)"))
    return pd.DataFrame(rows), agg


# ---------------------------------------------------------------- RM vs rest tests
def rate_ratio(d1, e1, d0, e0):
    """Exact conditional test for the ratio of two Poisson rates (d/e)."""
    tot = d1 + d0
    bt = stats.binomtest(int(d1), int(tot), e1 / (e1 + e0), alternative="greater")
    rr = (d1 / e1) / (d0 / e0)
    ci = stats.binomtest(int(d1), int(tot), e1 / (e1 + e0)).proportion_ci(confidence_level=0.95)
    f = lambda p: (p / (1 - p)) * (e0 / e1)
    return rr, f(ci.low), f(ci.high), bt.pvalue


def rm_vs_rest(tm, scope_name, mask):
    t = tm[mask]
    rows = []
    for lab, col in (("per match played", None), ("per 100 shots", "shots"), ("per 100 shots on target", "sot"),
                     ("per 10 xG", "xg"), ("per 100 offsides", "offsides"), ("per 100 corners", "corners"),
                     ("per 100 goal events (goals + nullified)", "goal_events")):
        t = t.copy()
        t["goal_events"] = t.gf + t.dis
        r = t[t.team == RM]
        o = t[t.team != RM]
        ex = (lambda x: len(x)) if col is None else (lambda x, c=col: x[c].sum())
        e1, e0 = ex(r), ex(o)
        d1, d0 = r.dis.sum(), o.dis.sum()
        rr, lo, hi, p = rate_ratio(d1, e1, d0, e0)
        scale = {None: 1, "shots": 100, "sot": 100, "xg": 10, "offsides": 100, "corners": 100, "goal_events": 100}[col]
        rows.append(dict(scope=scope_name, exposure=lab, rm_nullified=int(d1), rm_exposure=float(e1),
                         rm_rate=scale * d1 / e1, others_nullified=int(d0), others_exposure=float(e0),
                         others_rate=scale * d0 / e0, rate_ratio=rr, rr_ci_low=lo, rr_ci_high=hi, p_one_sided=p))
    return pd.DataFrame(rows)


def glm_models(tm, scope_name, mask):
    t = tm[mask].dropna(subset=["shots", "offsides", "xg", "sot"]).copy()
    t["is_rm"] = (t.team == RM).astype(int)
    t["home"] = (t.venue == "H").astype(int)
    t["l_off"] = np.log1p(t.offsides)
    t["l_shots"] = np.log1p(t.shots)
    t["l_sot"] = np.log1p(t.sot)
    t["xg_"] = t.xg
    specs = [("M0 raw: RM indicator only", "dis ~ is_rm"),
             ("M1 + offsides", "dis ~ is_rm + l_off"),
             ("M2 + shots", "dis ~ is_rm + l_shots"),
             ("M3 + shots on target", "dis ~ is_rm + l_sot"),
             ("M4 + xG", "dis ~ is_rm + xg_"),
             ("M5 + offsides + shots", "dis ~ is_rm + l_off + l_shots"),
             ("M6 + offsides + shots + xG + home + season FE", "dis ~ is_rm + l_off + l_shots + xg_ + home + C(season)")]
    rows = []
    for name, f in specs:
        m = smf.glm(f, t, family=sm.families.Poisson()).fit(cov_type="cluster", cov_kwds={"groups": t.fs_id.astype("category").cat.codes})
        b, se = m.params["is_rm"], m.bse["is_rm"]
        rows.append(dict(scope=scope_name, model=name, n_team_matches=len(t), rm_irr=np.exp(b),
                         irr_ci_low=np.exp(b - 1.96 * se), irr_ci_high=np.exp(b + 1.96 * se), p_value=m.pvalues["is_rm"],
                         pearson_dispersion=m.pearson_chi2 / m.df_resid, aic=m.aic,
                         off_coef=m.params.get("l_off", np.nan), off_p=m.pvalues.get("l_off", np.nan),
                         shots_coef=m.params.get("l_shots", np.nan), shots_p=m.pvalues.get("l_shots", np.nan)))
    return pd.DataFrame(rows)


def leave_rm_out_forecast(tm, scope_name, mask, n_sim=20000):
    """Fit the 'attack volume' model without RM, then ask how likely RM's observed total is under that model."""
    t = tm[mask].dropna(subset=["shots", "offsides", "xg", "sot"]).copy()
    t["home"] = (t.venue == "H").astype(int)
    t["l_off"] = np.log1p(t.offsides)
    t["l_shots"] = np.log1p(t.shots)
    t["xg_"] = t.xg
    rows = []
    for name, f in (("matches only (league average rate)", "dis ~ 1"),
                    ("offsides", "dis ~ l_off + home"), ("shots", "dis ~ l_shots + home"),
                    ("xG", "dis ~ xg_ + home"), ("offsides + shots + xG", "dis ~ l_off + l_shots + xg_ + home")):
        tr = t[t.team != RM]
        m = smf.glm(f, tr, family=sm.families.Poisson()).fit()
        r = t[t.team == RM]
        lam = m.predict(r).values
        # allow for over-dispersion with a gamma-Poisson (NB) draw using the pearson dispersion of the training fit
        disp = max(m.pearson_chi2 / m.df_resid, 1.0)
        k = lam.sum() / max(disp - 1, 1e-6)
        sims = rng.poisson(rng.gamma(shape=k, scale=lam.sum() / k, size=n_sim)) if disp > 1.01 else rng.poisson(lam.sum(), n_sim)
        obs = int(r.dis.sum())
        rows.append(dict(scope=scope_name, model_trained_on_other_teams=name, rm_matches=len(r), rm_observed=obs,
                         rm_expected=lam.sum(), expected_p2_5=np.percentile(sims, 2.5), expected_p97_5=np.percentile(sims, 97.5),
                         excess=obs - lam.sum(), obs_over_expected=obs / lam.sum(),
                         p_value_obs_or_more=(np.sum(sims >= obs) + 1) / (n_sim + 1), dispersion_used=disp))
    return pd.DataFrame(rows)


def within_match_symmetry(tm):
    """In every RM match both teams share the same referee, VAR team and conditions."""
    a = tm[tm.team == RM][["fs_id", "season", "opponent", "dis", "offsides", "shots", "xg", "gf", "ga"]].rename(
        columns={"dis": "dis_rm", "offsides": "off_rm", "shots": "shots_rm", "xg": "xg_rm", "gf": "gf_rm", "ga": "ga_rm"})
    b = tm[tm.opponent == RM][["fs_id", "dis", "offsides", "shots", "xg"]].rename(
        columns={"dis": "dis_opp", "offsides": "off_opp", "shots": "shots_opp", "xg": "xg_opp"})
    m = a.merge(b, on="fs_id")
    rows = []
    for lab, num, den in (("offsides", "off_rm", "off_opp"), ("shots", "shots_rm", "shots_opp"), ("xG", "xg_rm", "xg_opp"),
                          ("goal opportunities (goals+nullified)", None, None)):
        if num:
            s = m[num] / (m[num] + m[den]).replace(0, np.nan)
        else:
            s = (m.gf_rm + m.dis_rm) / ((m.gf_rm + m.dis_rm) + (m.ga_rm + m.dis_opp)).replace(0, np.nan)
        s = s.fillna(0.5)
        tot = (m.dis_rm + m.dis_opp).astype(int)
        obs = int(m.dis_rm.sum())
        sims = np.array([rng.binomial(tot.values, s.values).sum() for _ in range(20000)])
        rows.append(dict(null_model=f"RM share of nullified goals in RM matches ~ RM share of {lab}",
                         rm_matches=len(m), nullified_rm=obs, nullified_opponents=int(m.dis_opp.sum()),
                         expected_rm=float(sims.mean()), expected_p2_5=np.percentile(sims, 2.5),
                         expected_p97_5=np.percentile(sims, 97.5), p_value_rm_obs_or_more=(np.sum(sims >= obs) + 1) / 20001,
                         rm_share_of_nullified=obs / tot.sum(), mean_rm_attack_share=float((s * tot).sum() / tot.sum())))
    return pd.DataFrame(rows), m


def opponents_favoured(tm):
    """Favouritism test: do RM's opponents get fewer goals nullified against RM than in their other matches?"""
    t = tm.copy()
    vs = t[t.opponent == RM]
    rows = []
    exp_m, exp_o, exp_s = 0.0, 0.0, 0.0
    for r in vs.itertuples():
        oth = t[(t.team == r.team) & (t.season == r.season) & (t.opponent != RM)]
        if len(oth) == 0:
            continue
        exp_m += oth.dis.mean()
        exp_o += oth.dis.sum() / max(oth.offsides.sum(), 1) * r.offsides
        exp_s += oth.dis.sum() / max(oth.shots.sum(), 1) * r.shots
    obs = int(vs.dis.sum())
    out = []
    for lab, e in (("their own per-match rate that season", exp_m), ("their own per-offside rate that season", exp_o),
                   ("their own per-shot rate that season", exp_s)):
        p_less = stats.poisson.cdf(obs, e)
        out.append(dict(baseline=lab, matches_vs_rm=len(vs), nullified_for_opponents_in_rm_matches=obs, expected=e,
                        ratio_obs_over_exp=obs / e, p_value_fewer_than_expected=p_less))
    return pd.DataFrame(out)


def referee_table(tm, mt, d):
    ref = mt.set_index("fs_id").referee
    t = tm.copy()
    t["referee"] = t.fs_id.map(ref)
    rm = t[t.team == RM]
    oth = t[t.team != RM]
    g = rm.groupby("referee").agg(rm_matches=("fs_id", "size"), rm_nullified=("dis", "sum"), rm_offsides=("offsides", "sum")).reset_index()
    o = oth.groupby("referee").agg(other_team_matches=("fs_id", "size"), other_nullified=("dis", "sum")).reset_index()
    g = g.merge(o, on="referee", how="left")
    g["rm_per_match"] = g.rm_nullified / g.rm_matches
    g["others_per_team_match_same_ref"] = g.other_nullified / g.other_team_matches
    g["ratio_rm_vs_others_same_ref"] = g.rm_per_match / g.others_per_team_match_same_ref
    g = g.sort_values("rm_matches", ascending=False)
    # homogeneity of RM's rate across referees (Poisson heterogeneity chi-square) using refs with >=8 RM matches
    big = g[g.rm_matches >= 8]
    lam = big.rm_nullified.sum() / big.rm_matches.sum()
    chi = ((big.rm_nullified - lam * big.rm_matches) ** 2 / (lam * big.rm_matches)).sum()
    pchi = 1 - stats.chi2.cdf(chi, len(big) - 1)
    # within-referee evidence: RM excess vs same-referee baseline
    refs_with_excess = int((big.ratio_rm_vs_others_same_ref > 1).sum())
    meta = pd.DataFrame([dict(refs_with_8plus_rm_matches=len(big), chi2_heterogeneity=chi, dof=len(big) - 1, p_value=pchi,
                              refs_where_rm_rate_exceeds_same_ref_baseline=refs_with_excess)])
    return g, meta


def net_points_ledger(d):
    """Counterfactual: points each team lost from its own nullified goals vs points it kept because an opponent's goal was nullified."""
    x = d[d.var_confirmed].copy()
    x["opp_gf"], x["opp_ga"] = x.team_ga, x.team_gf
    pts = lambda a, b: 3 if a > b else 1 if a == b else 0
    x["opp_pts_saved"] = [pts(a, b) - pts(a, b + 1) for a, b in zip(x.opp_gf, x.opp_ga)]
    lost = x.groupby("team").agg(own_nullified=("fs_id", "size"), points_lost=("points_lost", "sum"),
                                 matches_result_changed=("result_changed", "sum")).reset_index()
    kept = x.groupby("opponent").agg(opp_nullified_against_them=("fs_id", "size"), points_kept=("opp_pts_saved", "sum")).reset_index().rename(columns={"opponent": "team"})
    L = lost.merge(kept, on="team", how="outer").fillna(0)
    L["net_points_from_nullified_goals"] = L.points_kept - L.points_lost
    return L.sort_values("net_points_from_nullified_goals", ascending=False)


def var_accuracy_scenarios(n_rm, expected, observed):
    rows = []
    for lab, acc in (("Spitz et al. 2021 (13 countries): 98.3%", 0.983), ("Premier League claim: 96%", 0.96),
                     ("Task floor: 95%", 0.95), ("Stress test: 90%", 0.90), ("Stress test: 80%", 0.80)):
        err = 1 - acc
        exp_err = n_rm * err
        p10 = 1 - stats.binom.cdf(9, n_rm, err)
        pex = 1 - stats.binom.cdf(max(int(round(observed - expected)) - 1, 0), n_rm, err)
        rows.append(dict(accuracy_scenario=lab, assumed_error_rate=err, rm_decisions=n_rm,
                         expected_wrong_rm_decisions=exp_err, p_at_least_10_wrong=p10,
                         excess_to_explain=round(observed - expected, 1),
                         p_wrong_decisions_ge_excess=pex))
    return pd.DataFrame(rows)


def espn_independent_check(d):
    """ESPN's own 'GOAL OVERTURNED BY VAR' log (2023-24 onwards) vs Flashscore, team by team."""
    es = pd.read_csv(os.path.join(P, "espn_matches.csv"))
    es["season_start"] = pd.to_datetime(es.kickoff_utc).apply(lambda t: t.year if t.month >= 7 else t.year - 1)
    rows = []
    for r in es.itertuples():
        for kind, mn, txt in json.loads(r.espn_var_events):
            if kind == "overturned":
                m = re.search(r"VAR: .*? \((.+?)\) scores", txt)
                if m:
                    rows.append(dict(season_start=r.season_start, team=m.group(1)))
    e = pd.DataFrame(rows)
    e = e[e.season_start >= 2023]
    canon = sorted(set(d.team) | set(d.opponent))
    kk = lambda s: re.sub(r"[^a-z]", "", "".join(c for c in __import__("unicodedata").normalize("NFKD", s) if not __import__("unicodedata").combining(c)).lower())

    def to_canon(n):
        k = kk(n)
        if k == "atleticomadrid":
            return "Atlético de Madrid"
        if k == "celtavigo":
            return "Celta de Vigo"
        for c in canon:
            if kk(c) == k:
                return c
        for c in canon:
            if k in kk(c) or kk(c) in k:
                return c
        return n

    e["team"] = e.team.map(to_canon)
    f = d[d.var_confirmed & (pd.to_datetime(d.kickoff).apply(lambda t: t.year if t.month >= 7 else t.year - 1) >= 2023)]
    out = pd.DataFrame({"espn_overturned_goals": e.team.value_counts(), "flashscore_nullified_goals": f.team.value_counts()}).fillna(0).astype(int)
    out["espn_rank"] = out.espn_overturned_goals.rank(ascending=False, method="min")
    out["flashscore_rank"] = out.flashscore_nullified_goals.rank(ascending=False, method="min")
    out["rm_share_espn_pct"] = np.nan
    out = out.sort_values("flashscore_nullified_goals", ascending=False)
    tot_e, tot_f = out.espn_overturned_goals.sum(), out.flashscore_nullified_goals.sum()
    out["share_espn_pct"] = 100 * out.espn_overturned_goals / tot_e
    out["share_flashscore_pct"] = 100 * out.flashscore_nullified_goals / tot_f
    return out.drop(columns="rm_share_espn_pct").reset_index().rename(columns={"index": "team"})


TWEET = {"Real Madrid": 42, "Atlético de Madrid": 22, "Villarreal": 22, "Celta de Vigo": 20, "Real Sociedad": 20,
         "Sevilla": 20, "FC Barcelona": 19}


def tweet_validation(d):
    x = d.copy()
    allc = x.team.value_counts()
    var = x[x.var_confirmed].team.value_counts()
    pre_today = x[x.var_confirmed & (pd.to_datetime(x.kickoff) < pd.Timestamp("2026-10-10"))].team.value_counts()
    off = x[x.var_confirmed & (x.reason_fs == "offside")].team.value_counts()
    of = x[x.var_confirmed & x.reason_fs.isin(["offside", "Foul"])].team.value_counts()
    rows = []
    for i, (t, v) in enumerate(TWEET.items(), 1):
        rows.append(dict(tweet_rank=i, team=t, tweet_count=v + (1 if t == "Real Madrid" else 0) if False else v,
                         reconstructed_all_flashscore=int(allc.get(t, 0)), reconstructed_var_confirmed=int(var.get(t, 0)),
                         reconstructed_before_10_oct_2026=int(pre_today.get(t, 0)),
                         offside_only=int(off.get(t, 0)), offside_plus_foul=int(of.get(t, 0))))
    r = pd.DataFrame(rows)
    r["diff_vs_tweet"] = r.reconstructed_before_10_oct_2026 - r.tweet_count
    r["diff_pct"] = 100 * r.diff_vs_tweet / r.tweet_count
    r["reconstructed_rank_all_teams"] = [int(var.rank(ascending=False, method="min")[t]) for t in r.team]
    return r


def cluster_check(tm):
    """Are RM's totals driven by a few multi-goal matches? Compare P(match has >=1 nullified goal)."""
    t = tm.copy()
    t["any"] = (t.dis > 0).astype(int)
    rows = []
    for nm, mask in (("All 20 teams per season", t.fs_id.notna()), ("Top-10 teams per season", t.top10 == True)):
        s = t[mask]
        r, o = s[s.team == RM], s[s.team != RM]
        a, b, c, dd = int(r["any"].sum()), len(r) - int(r["any"].sum()), int(o["any"].sum()), len(o) - int(o["any"].sum())
        orr, p = stats.fisher_exact([[a, b], [c, dd]], alternative="greater")
        rows.append(dict(scope=nm, rm_matches_with_nullified=a, rm_matches=len(r), rm_pct=100 * a / len(r),
                         others_matches_with_nullified=c, others_team_matches=len(o), others_pct=100 * c / len(o),
                         odds_ratio=orr, p_one_sided=p, rm_max_nullified_in_one_match=int(r.dis.max()),
                         rm_nullified_in_multi_goal_matches=int(r[r.dis >= 2].dis.sum())))
    return pd.DataFrame(rows)


def ppda_models(tm, scope_name, mask, n_sim=20000):
    """Does adding pressing context (PPDA att and def, own and opponent's) absorb the Real Madrid effect?
    All specs are fitted on the same PPDA-complete sample so the RM coefficients are comparable."""
    t = tm[mask].dropna(subset=["shots", "offsides", "xg", "sot", "ppda_att", "ppda_def", "opp_ppda_att", "opp_ppda_def"]).copy()
    t["is_rm"] = (t.team == RM).astype(int)
    t["home"] = (t.venue == "H").astype(int)
    t["l_off"], t["l_shots"], t["xg_"] = np.log1p(t.offsides), np.log1p(t.shots), t.xg
    t["l_pa"], t["l_pd"] = np.log(t.ppda_att), np.log(t.ppda_def)
    t["l_opa"], t["l_opd"] = np.log(t.opp_ppda_att), np.log(t.opp_ppda_def)
    base = "dis ~ is_rm + l_off + l_shots + xg_ + home + C(season)"
    specs = [("Reference (offsides + shots + xG + home + season FE), PPDA-complete sample", base),
             ("+ own PPDA att and def", base + " + l_pa + l_pd"),
             ("+ opponent PPDA att and def", base + " + l_opa + l_opd"),
             ("+ own and opponent PPDA att and def", base + " + l_pa + l_pd + l_opa + l_opd")]
    groups = t.fs_id.astype("category").cat.codes
    glm_rows, coef_rows = [], []
    for name, f in specs:
        m = smf.glm(f, t, family=sm.families.Poisson()).fit(cov_type="cluster", cov_kwds={"groups": groups})
        b, se = m.params["is_rm"], m.bse["is_rm"]
        glm_rows.append(dict(scope=scope_name, model=name, n_team_matches=len(t), rm_irr=np.exp(b),
                             irr_ci_low=np.exp(b - 1.96 * se), irr_ci_high=np.exp(b + 1.96 * se), p_value=m.pvalues["is_rm"],
                             aic=m.aic, pearson_dispersion=m.pearson_chi2 / m.df_resid))
        if name.startswith("+ own and opponent"):
            for v, lab in (("l_off", "log(offsides + 1)"), ("l_shots", "log(shots + 1)"), ("xg_", "xG"), ("home", "home"),
                           ("l_pa", "log(own PPDA att)"), ("l_pd", "log(own PPDA def)"),
                           ("l_opa", "log(opponent PPDA att)"), ("l_opd", "log(opponent PPDA def)"), ("is_rm", "Real Madrid")):
                coef_rows.append(dict(scope=scope_name, variable=lab, coef=m.params[v], irr=np.exp(m.params[v]),
                                      ci_low=np.exp(m.params[v] - 1.96 * m.bse[v]), ci_high=np.exp(m.params[v] + 1.96 * m.bse[v]),
                                      p_value=m.pvalues[v]))
    # leave-RM-out forecast with the full PPDA model
    tr = t[t.team != RM]
    f_full = base + " + l_pa + l_pd + l_opa + l_opd"
    m0 = smf.glm(f_full.replace("is_rm + ", ""), tr, family=sm.families.Poisson()).fit()
    r = t[t.team == RM]
    lam = m0.predict(r).values
    disp = max(m0.pearson_chi2 / m0.df_resid, 1.0)
    k = lam.sum() / max(disp - 1, 1e-6)
    sims = rng.poisson(rng.gamma(shape=k, scale=lam.sum() / k, size=n_sim)) if disp > 1.01 else rng.poisson(lam.sum(), n_sim)
    obs = int(r.dis.sum())
    fc = dict(scope=scope_name, model_trained_on_other_teams="offsides + shots + xG + own & opponent PPDA (att, def)",
              rm_matches=len(r), rm_observed=obs, rm_expected=lam.sum(), expected_p2_5=np.percentile(sims, 2.5),
              expected_p97_5=np.percentile(sims, 97.5), excess=obs - lam.sum(), obs_over_expected=obs / lam.sum(),
              p_value_obs_or_more=(np.sum(sims >= obs) + 1) / (n_sim + 1), dispersion_used=disp)
    return pd.DataFrame(glm_rows), pd.DataFrame(coef_rows), pd.DataFrame([fc])


def ppda_profile(tm):
    """Real Madrid vs other teams (top-10 and all): pressing and the pressing it faces, per match."""
    rows = []
    for nm, mask in (("All 20 teams per season", tm.fs_id.notna()), ("Top-10 teams per season", tm.top10 == True)):
        t = tm[mask].dropna(subset=["ppda_att", "ppda_def", "opp_ppda_att", "opp_ppda_def"])
        for lab, grp in (("Real Madrid", t[t.team == RM]), ("Other teams", t[t.team != RM])):
            rows.append(dict(scope=nm, group=lab, team_matches=len(grp),
                             ppda_att=grp.ppda_att.mean(), ppda_def=grp.ppda_def.mean(),
                             ppda=grp.ppda_att.sum() / grp.ppda_def.sum(),
                             opp_ppda_att=grp.opp_ppda_att.mean(), opp_ppda_def=grp.opp_ppda_def.mean(),
                             opp_ppda=grp.opp_ppda_att.sum() / grp.opp_ppda_def.sum(),
                             nullified_per_match=grp.dis.mean()))
    return pd.DataFrame(rows)


def discipline_models(tm, scope_name, mask, n_sim=20000):
    """Adds fouls / fouls in the attacking half / yellow / red cards to the Real Madrid model.
    Same discipline-complete sample (ESPN foul zones available) for every spec."""
    cols = ["shots", "offsides", "xg", "fouls", "fouls_att_half", "yellow", "red", "ppda_att", "ppda_def", "opp_ppda_att", "opp_ppda_def"]
    t = tm[mask].dropna(subset=cols).copy()
    t["is_rm"] = (t.team == RM).astype(int)
    t["home"] = (t.venue == "H").astype(int)
    t["l_off"], t["l_shots"], t["xg_"] = np.log1p(t.offsides), np.log1p(t.shots), t.xg
    t["l_f"], t["l_fa"] = np.log1p(t.fouls), np.log1p(t.fouls_att_half)
    t["l_pa"], t["l_pd"] = np.log(t.ppda_att), np.log(t.ppda_def)
    t["l_opa"], t["l_opd"] = np.log(t.opp_ppda_att), np.log(t.opp_ppda_def)
    base = "dis ~ is_rm + l_off + l_shots + xg_ + home + C(season)"
    ppda = " + l_pa + l_pd + l_opa + l_opd"
    specs = [("Reference (offsides + shots + xG + home + season FE)", base),
             ("+ total fouls committed", base + " + l_f"),
             ("+ fouls committed in attacking half", base + " + l_fa"),
             ("+ yellow cards + red cards", base + " + yellow + red"),
             ("+ total fouls + yellow + red", base + " + l_f + yellow + red"),
             ("+ attacking-half fouls + yellow + red", base + " + l_fa + yellow + red"),
             ("+ total fouls + attacking-half fouls + yellow + red", base + " + l_f + l_fa + yellow + red"),
             ("Full: + fouls (total, attacking half) + yellow + red + own & opponent PPDA", base + " + l_f + l_fa + yellow + red" + ppda)]
    groups = t.fs_id.astype("category").cat.codes
    rows, coefs = [], []
    for name, f in specs:
        m = smf.glm(f, t, family=sm.families.Poisson()).fit(cov_type="cluster", cov_kwds={"groups": groups})
        b, se = m.params["is_rm"], m.bse["is_rm"]
        rows.append(dict(scope=scope_name, model=name, n_team_matches=len(t), rm_irr=np.exp(b), irr_ci_low=np.exp(b - 1.96 * se),
                         irr_ci_high=np.exp(b + 1.96 * se), p_value=m.pvalues["is_rm"], aic=m.aic,
                         pearson_dispersion=m.pearson_chi2 / m.df_resid))
        if name.startswith("Full"):
            lab = {"l_off": "log(offsides + 1)", "l_shots": "log(shots + 1)", "xg_": "xG", "home": "home", "l_f": "log(fouls committed + 1)",
                   "l_fa": "log(fouls in attacking half + 1)", "yellow": "yellow cards (per card)", "red": "red cards (per card)",
                   "l_pa": "log(own PPDA att)", "l_pd": "log(own PPDA def)", "l_opa": "log(opp. PPDA att)", "l_opd": "log(opp. PPDA def)", "is_rm": "Real Madrid"}
            for v, lb in lab.items():
                coefs.append(dict(scope=scope_name, variable=lb, coef=m.params[v], irr=np.exp(m.params[v]),
                                  ci_low=np.exp(m.params[v] - 1.96 * m.bse[v]), ci_high=np.exp(m.params[v] + 1.96 * m.bse[v]), p_value=m.pvalues[v]))
    tr, r = t[t.team != RM], t[t.team == RM]
    m0 = smf.glm(specs[-1][1].replace("is_rm + ", ""), tr, family=sm.families.Poisson()).fit()
    lam = m0.predict(r).values
    disp = max(m0.pearson_chi2 / m0.df_resid, 1.0)
    k = lam.sum() / max(disp - 1, 1e-6)
    sims = rng.poisson(rng.gamma(shape=k, scale=lam.sum() / k, size=n_sim)) if disp > 1.01 else rng.poisson(lam.sum(), n_sim)
    obs = int(r.dis.sum())
    fc = dict(scope=scope_name, model_trained_on_other_teams="Full discipline + PPDA model", rm_matches=len(r), rm_observed=obs,
              rm_expected=lam.sum(), expected_p2_5=np.percentile(sims, 2.5), expected_p97_5=np.percentile(sims, 97.5), excess=obs - lam.sum(),
              obs_over_expected=obs / lam.sum(), p_value_obs_or_more=(np.sum(sims >= obs) + 1) / (n_sim + 1), dispersion_used=disp)
    return pd.DataFrame(rows), pd.DataFrame(coefs), pd.DataFrame([fc])


def discipline_profile(tm):
    rows = []
    for nm, mask in (("All 20 teams per season", tm.fs_id.notna()), ("Top-10 teams per season", tm.top10 == True)):
        t = tm[mask].dropna(subset=["fouls", "fouls_att_half", "yellow", "red"])
        for lab, g_ in (("Real Madrid", t[t.team == RM]), ("Other teams", t[t.team != RM])):
            rows.append(dict(scope=nm, group=lab, team_matches=len(g_), fouls=g_.fouls.mean(), fouls_att_half=g_.fouls_att_half.mean(),
                             fouls_def_half=g_.fouls_def_half.mean(), fouls_wing=g_.fouls_wing.mean(), fouls_own_box=g_.fouls_own_box.mean(),
                             att_half_share=g_.fouls_att_half.sum() / g_.fouls_located.sum(), yellow=g_.yellow.mean(), red=g_.red.mean(),
                             nullified_per_match=g_.dis.mean()))
    return pd.DataFrame(rows)


def reason_rates(tm):
    """Where does Real Madrid's excess come from? Nullified goals per match by VAR reason, RM vs other teams."""
    rows = []
    for nm, mask in (("All 20 teams per season", tm.fs_id.notna()), ("Top-10 teams per season", tm.top10 == True)):
        t = tm[mask]
        r, o = t[t.team == RM], t[t.team != RM]
        for lab, col in (("Offside", "dis_offside"), ("Attacking foul", "dis_Foul"), ("Handball", "dis_handball"),
                         ("Video review (unspecified)", "dis_video_review"), ("All reasons", "dis")):
            d1, d0 = int(r[col].sum()), int(o[col].sum())
            rr, lo, hi, p = rate_ratio(d1, len(r), d0, len(o)) if d1 > 0 and d0 > 0 else (np.nan,) * 4
            rows.append(dict(scope=nm, reason=lab, rm_nullified=d1, rm_per_match=d1 / len(r), others_nullified=d0,
                             others_per_match=d0 / len(o), rate_ratio=rr, rr_ci_low=lo, rr_ci_high=hi, p_one_sided=p))
    return pd.DataFrame(rows)


def onfield_analysis(tm):
    """Goals ruled out on the pitch without VAR (assistant flag / referee whistle) and the combined 'any disallowed' count."""
    rows, glm_rows = [], []
    for nm, mask in (("All 20 teams per season", tm.fs_id.notna()), ("Top-10 teams per season", tm.top10 == True)):
        t = tm[mask]
        r, o = t[t.team == RM], t[t.team != RM]
        for cat, col in (("On-field only (no VAR)", "onf"), ("VAR-nullified only", "dis"), ("Combined (on-field + VAR)", "any_disallowed")):
            for lab, ex in (("per match played", None), ("per 100 offsides", "offsides"), ("per 100 shots", "shots")):
                e1 = len(r) if ex is None else r[ex].sum()
                e0 = len(o) if ex is None else o[ex].sum()
                d1, d0 = int(r[col].sum()), int(o[col].sum())
                rr, lo, hi, p = rate_ratio(d1, e1, d0, e0)
                sc = 1 if ex is None else 100
                rows.append(dict(scope=nm, category=cat, exposure=lab, rm_events=d1, rm_rate=sc * d1 / e1, others_events=d0,
                                 others_rate=sc * d0 / e0, rate_ratio=rr, rr_ci_low=lo, rr_ci_high=hi, p_one_sided=p))
        for cat, col in (("On-field only (no VAR)", "onf"), ("Combined (on-field + VAR)", "any_disallowed")):
            x = t.dropna(subset=["shots", "offsides", "xg"]).copy()
            x["is_rm"] = (x.team == RM).astype(int)
            x["home"] = (x.venue == "H").astype(int)
            x["l_off"], x["l_shots"], x["xg_"] = np.log1p(x.offsides), np.log1p(x.shots), x.xg
            for lab, f in (("Raw (RM indicator)", f"{col} ~ is_rm"), ("+ offsides + shots + xG + home + season FE", f"{col} ~ is_rm + l_off + l_shots + xg_ + home + C(season)")):
                m = smf.glm(f, x, family=sm.families.Poisson()).fit(cov_type="cluster", cov_kwds={"groups": x.fs_id.astype("category").cat.codes})
                b, se = m.params["is_rm"], m.bse["is_rm"]
                glm_rows.append(dict(scope=nm, category=cat, model=lab, rm_irr=np.exp(b), irr_ci_low=np.exp(b - 1.96 * se),
                                     irr_ci_high=np.exp(b + 1.96 * se), p_value=m.pvalues["is_rm"]))
    # Does the VAR stage treat Real Madrid differently from the on-field stage? stacked counts with a RM x VAR interaction
    inter = []
    for nm, mask in (("All 20 teams per season", tm.fs_id.notna()), ("Top-10 teams per season", tm.top10 == True)):
        x = tm[mask].dropna(subset=["shots", "offsides", "xg"]).copy()
        x["is_rm"] = (x.team == RM).astype(int)
        x["home"] = (x.venue == "H").astype(int)
        x["l_off"], x["l_shots"], x["xg_"] = np.log1p(x.offsides), np.log1p(x.shots), x.xg
        keep = ["fs_id", "team", "season", "is_rm", "home", "l_off", "l_shots", "xg_"]
        a = x[keep + ["onf"]].rename(columns={"onf": "n"}).assign(is_var=0)
        b = x[keep + ["dis"]].rename(columns={"dis": "n"}).assign(is_var=1)
        s = pd.concat([a, b], ignore_index=True)
        grp = s.fs_id.astype("category").cat.codes
        for lab, f in (("Raw", "n ~ is_rm * is_var"), ("Controlled (offsides, shots, xG, home, season FE)", "n ~ is_rm * is_var + l_off + l_shots + xg_ + home + C(season)")):
            m = smf.glm(f, s, family=sm.families.Poisson()).fit(cov_type="cluster", cov_kwds={"groups": grp})
            for term, tl in (("is_rm", "Real Madrid effect on on-field disallowed goals (IRR)"),
                             ("is_rm:is_var", "Extra Real Madrid effect at the VAR stage vs on-field (IRR ratio)")):
                b_, se = m.params[term], m.bse[term]
                inter.append(dict(scope=nm, model=lab, term=tl, irr=np.exp(b_), ci_low=np.exp(b_ - 1.96 * se), ci_high=np.exp(b_ + 1.96 * se), p_value=m.pvalues[term]))
    OUT["onf_inter"] = pd.DataFrame(inter)
    tt = tm.groupby("team").agg(matches=("fs_id", "size"), var_nullified=("dis", "sum"), onfield=("onf", "sum"),
                                combined=("any_disallowed", "sum"), goals=("gf", "sum")).reset_index()
    tt["onfield_per_match"] = tt.onfield / tt.matches
    tt["combined_per_match"] = tt.combined / tt.matches
    tt["share_of_combined_that_was_var_pct"] = 100 * tt.var_nullified / tt.combined.replace(0, np.nan)
    tt["rank_combined"] = tt.combined.rank(ascending=False, method="min").astype(int)
    tt["rank_onfield"] = tt.onfield.rank(ascending=False, method="min").astype(int)
    tt["rank_var"] = tt.var_nullified.rank(ascending=False, method="min").astype(int)
    return pd.DataFrame(rows), pd.DataFrame(glm_rows), tt.sort_values("combined", ascending=False)


def main():
    tm, d, mt, ft = load()
    tm = add_d_to_tm(tm, d)
    OUT["tm"], OUT["d"], OUT["mt"], OUT["ft"] = tm, d, mt, ft
    OUT["espn_check"] = espn_independent_check(d)
    OUT["tweet_val"] = tweet_validation(d)
    OUT["stat_validation"] = validate_stats(tm)
    ts = team_season(tm)
    OUT["ts"] = ts
    OUT["corr"], OUT["top10_agg"] = correlations(ts)
    rows = []
    for nm, mask in (("All 20 teams per season", tm.fs_id.notna()), ("Top-10 teams per season (final table)", tm.top10 == True)):
        rows.append(rm_vs_rest(tm, nm, mask))
    OUT["rate_tests"] = pd.concat(rows, ignore_index=True)
    OUT["glm"] = pd.concat([glm_models(tm, nm, mask) for nm, mask in (("All 20 teams per season", tm.fs_id.notna()), ("Top-10 teams per season", tm.top10 == True))], ignore_index=True)
    scopes = (("All 20 teams per season", tm.fs_id.notna()), ("Top-10 teams per season", tm.top10 == True))
    pm = [ppda_models(tm, nm, mask) for nm, mask in scopes]
    OUT["ppda_glm"] = pd.concat([x[0] for x in pm], ignore_index=True)
    OUT["ppda_coef"] = pd.concat([x[1] for x in pm], ignore_index=True)
    OUT["ppda_fc"] = pd.concat([x[2] for x in pm], ignore_index=True)
    OUT["ppda_profile"] = ppda_profile(tm)
    OUT["onf_rates"], OUT["onf_glm"], OUT["onf_teams"] = onfield_analysis(tm)
    dm = [discipline_models(tm, nm, mask) for nm, mask in scopes]
    OUT["disc_glm"] = pd.concat([x[0] for x in dm], ignore_index=True)
    OUT["disc_coef"] = pd.concat([x[1] for x in dm], ignore_index=True)
    OUT["disc_fc"] = pd.concat([x[2] for x in dm], ignore_index=True)
    OUT["disc_profile"] = discipline_profile(tm)
    OUT["reason_rates"] = reason_rates(tm)
    OUT["forecast"] = pd.concat([leave_rm_out_forecast(tm, nm, mask) for nm, mask in (("All 20 teams per season", tm.fs_id.notna()), ("Top-10 teams per season", tm.top10 == True))], ignore_index=True)
    OUT["symmetry"], OUT["sym_matches"] = within_match_symmetry(tm)
    OUT["fav"] = opponents_favoured(tm)
    OUT["cluster"] = cluster_check(tm)
    OUT["ref"], OUT["ref_meta"] = referee_table(tm, mt, d)
    OUT["ledger"] = net_points_ledger(d)
    f = OUT["forecast"]
    base = f[(f.scope == "All 20 teams per season") & (f.model_trained_on_other_teams == "offsides + shots + xG")].iloc[0]
    OUT["acc"] = var_accuracy_scenarios(int(tm[tm.team == RM].dis.sum()), base.rm_expected, base.rm_observed)
    pickle.dump(OUT, open(os.path.join(P, "analysis.pkl"), "wb"))
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_colwidth", 60)
    for k in ("onf_rates", "onf_glm", "onf_teams", "disc_profile", "reason_rates", "disc_glm", "disc_coef", "disc_fc", "ppda_profile", "ppda_glm", "ppda_coef", "ppda_fc", "tweet_val", "espn_check", "stat_validation", "rate_tests", "glm", "forecast", "symmetry", "fav", "ref_meta", "acc"):
        print("\n=====", k)
        print(OUT[k].round(4).to_string())
    print("\n===== corr (selected)")
    print(OUT["corr"].round(3).to_string())
    print("\n===== ledger"); print(OUT["ledger"].round(1).head(12).to_string())


if __name__ == "__main__":
    main()
