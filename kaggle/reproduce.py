"""Reproduce the Real Madrid VAR-nullified goals analysis and its sensitivity analyses.

Usage (from the repository root, Python 3.12, no network needed):

    python kaggle/reproduce.py        # tables (CSV/JSON) -> kaggle/outputs/
    python kaggle/make_figures.py     # figures used in the Kaggle PDF -> kaggle/outputs/figures/

Inputs are the processed tables in data/processed/ (derived from public Flashscore, ESPN,
Transfermarkt and Understat feeds). Random seed: 2026.
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
OUT = Path(__file__).resolve().parent / "outputs"
RM = "Real Madrid"
SEED = 2026
ADJ = "is_rm + l_off + l_shots + xg_ + home + C(season)"  # offsides, shots, xG, home, season fixed effects

# --------------------------------------------------------------------------- data


def load():
    tm = pd.read_csv(P / "team_match.csv", parse_dates=["kickoff"])
    d = pd.read_csv(P / "disallowed_goals_enriched.csv", parse_dates=["kickoff"])
    onf = pd.read_csv(P / "onfield_disallowed_events.csv")
    res = pd.read_csv(P / "matches.csv")
    return tm, d, onf, res


def classify_events(d):
    """Evidence tiers for each Flashscore 'Goal Disallowed' incident.

    var_confirmed (draft definition) = Flashscore VAR wording OR ESPN review-type event within 3 minutes.
    No feed records the initial on-field decision as a field, so the tiers rest on commentary wording:
      T1 explicit overturn : a verdict line (no goal / disallowed / chalked off) AND a line showing the goal was
                             given or celebrated before the review (celebrations, 'review of the goal', 'changed
                             his mind', 'on the advice of the video assistant referee', 'intervention of the VAR')
      T2 VAR wording, unclear: VAR wording present, but only a review-in-progress line or only a verdict line
      T3 no explicit VAR text: kept only because an ESPN review-type event lies within 3 minutes, or because a
                             generic 'disallowed' commentary line set var_flag (1 Getafe event)
    """
    low = (d.fs_text.fillna("") + " || " + d.var_commentary.fillna("")).str.lower()
    d["text_var"] = low.str.contains(r"\bvar\b|video assistant|video review")  # explicit VAR wording (var_flag is looser)
    d["espn_ok"] = d.espn_corroborated == True  # noqa: E712
    d["var_confirmed"] = d.var_flag | d.text_var | d.espn_ok
    verdict = low.str.contains(r"no goal|disallow|chalked|won.t count")
    given = low.str.contains(r"celebrat|review (?:of )?the \w*\s?goal|review the .{0,20} goal|decided to review|subject to a var review"
                             r"|var review to see|changed his mind|after using var|advice of the video assistant|intervention of the var"
                             r"|signals a var review|legality of the goal|var signal")
    tier = np.where(~d.text_var, "T3 no explicit VAR text",
                    np.where(verdict & given, "T1 explicit overturn wording", "T2 VAR wording, initial decision unclear"))
    d["tier"] = tier
    return d


def definitions(d):
    """name -> boolean mask over the 397 Flashscore incidents."""
    v = d.var_confirmed
    return {
        "D0": v,
        "D1": d.text_var,
        "D2": v & d.tier.str.startswith("T1"),
        "D3": v & d.espn_ok,
        "D4": v & d.espn_ok & d.tier.str.startswith("T1"),
        "D5": v & (d.reason_fs == "offside"),
        "D6": v & d.reason_fs.isin(["offside", "Foul"]),
        "D7": v & (d.reason_fs != "video review"),
        "D8": pd.Series(True, index=d.index),
    }


DEF_LABEL = {
    "D0": "D0 Primary: VAR evidence in either feed (draft definition)",
    "D1": "D1 Explicit VAR wording in Flashscore text only",
    "D2": "D2 Explicit overturn wording (tier T1)",
    "D3": "D3 ESPN-corroborated only",
    "D4": "D4 Explicit wording and ESPN-corroborated",
    "D5": "D5 Offside reason only",
    "D6": "D6 Offside + attacking foul (the post's apparent scope)",
    "D7": "D7 Excluding 'unspecified video review'",
    "D8": "D8 All 397 Goal Disallowed incidents, no VAR requirement",
}


def build_panel(tm, d, onf):
    """Team-match panel with one outcome column per event definition."""
    defs = definitions(d)
    for name, mask in defs.items():
        c = d[mask].groupby(["fs_id", "team"]).size().rename(name)
        tm = tm.merge(c, left_on=["fs_id", "team"], right_index=True, how="left")
        tm[name] = tm[name].fillna(0).astype(int)
    oc = onf.groupby(["fs_id", "team"]).size().rename("onf")
    tm = tm.merge(oc, left_on=["fs_id", "team"], right_index=True, how="left")
    tm["onf"] = tm.onf.fillna(0).astype(int)
    for c in ("shots", "sot", "offsides", "xg"):
        tm[c] = pd.to_numeric(tm[c], errors="coerce")
    tm["is_rm"] = (tm.team == RM).astype(int)
    tm["home"] = (tm.venue == "H").astype(int)
    tm["l_off"], tm["l_shots"], tm["xg_"] = np.log1p(tm.offsides), np.log1p(tm.shots), tm.xg
    return tm, defs

# --------------------------------------------------------------------------- estimators


def rate_ratio(d1, e1, d0, e0):
    """Exact conditional test for the ratio of two Poisson rates (d / e)."""
    ci = stats.binomtest(int(d1), int(d1 + d0), e1 / (e1 + e0)).proportion_ci(confidence_level=0.95)
    f = lambda p: (p / (1 - p)) * (e0 / e1)
    return (d1 / e1) / (d0 / e0), f(ci.low), f(ci.high)


def fit_irr(t, y, term="is_rm", rhs=ADJ, cluster="fs_id"):
    """Poisson GLM, log link; IRR, 95% CI and p for `term` (cluster-robust SE)."""
    t = t.dropna(subset=["shots", "offsides", "xg", "sot"])
    g = t[cluster].astype("category").cat.codes if isinstance(cluster, str) else cluster(t)
    m = smf.glm(f"{y} ~ {rhs}", t, family=sm.families.Poisson()).fit(cov_type="cluster", cov_kwds={"groups": g})
    b, se = m.params[term], m.bse[term]
    return dict(irr=np.exp(b), lo=np.exp(b - 1.96 * se), hi=np.exp(b + 1.96 * se), p=m.pvalues[term],
                n=len(t), dispersion=m.pearson_chi2 / m.df_resid)


def team_season_groups(t):
    return (t.team + t.season).astype("category").cat.codes

# --------------------------------------------------------------------------- analyses


def headline(tm):
    r, o = tm[tm.is_rm == 1], tm[tm.is_rm == 0]
    rr, lo, hi = rate_ratio(r.D0.sum(), len(r), o.D0.sum(), len(o))
    adj = fit_irr(tm, "D0")
    raw = fit_irr(tm, "D0", rhs="is_rm")
    adj10 = fit_irr(tm[tm.top10 == True], "D0")  # noqa: E712
    nxt = tm[tm.team != RM].groupby("team").D0.sum().sort_values(ascending=False)
    return dict(rm_events=int(r.D0.sum()), rm_matches=len(r), rm_rate=r.D0.sum() / len(r),
                others_events=int(o.D0.sum()), others_matches=len(o), others_rate=o.D0.sum() / len(o),
                rate_ratio=rr, rr_lo=lo, rr_hi=hi, irr_raw=raw["irr"], irr_adj=adj["irr"], irr_adj_lo=adj["lo"],
                irr_adj_hi=adj["hi"], irr_adj_p=adj["p"], irr_adj_top10=adj10["irr"], next_team=nxt.index[0],
                next_team_events=int(nxt.iloc[0]), n_adj=adj["n"], dispersion=adj["dispersion"])


def var_stage(tm):
    """Stacked VAR / on-field counts: extra Real Madrid effect at the VAR stage."""
    x = tm.dropna(subset=["shots", "offsides", "xg"])
    keep = ["fs_id", "team", "season", "is_rm", "home", "l_off", "l_shots", "xg_"]
    a = x[keep + ["onf"]].rename(columns={"onf": "n"}).assign(is_var=0)
    b = x[keep + ["D0"]].rename(columns={"D0": "n"}).assign(is_var=1)
    s = pd.concat([a, b], ignore_index=True)
    m = smf.glm("n ~ is_rm * is_var + l_off + l_shots + xg_ + home + C(season)", s, family=sm.families.Poisson()).fit(
        cov_type="cluster", cov_kwds={"groups": s.fs_id.astype("category").cat.codes})
    out = {}
    for term, k in (("is_rm", "onfield"), ("is_rm:is_var", "var_extra")):
        bb, se = m.params[term], m.bse[term]
        out[k] = dict(irr=np.exp(bb), lo=np.exp(bb - 1.96 * se), hi=np.exp(bb + 1.96 * se), p=m.pvalues[term])
    return out


def _row(t, y, label, key):
    r, o = t[t.is_rm == 1], t[t.is_rm == 0]
    rr, lo, hi = rate_ratio(r[y].sum(), len(r), o[y].sum(), len(o))
    a = fit_irr(t, y)
    return dict(key=key, label=label, rm_events=int(r[y].sum()), others_events=int(o[y].sum()), rate_ratio=rr, rr_lo=lo,
                rr_hi=hi, adj_irr=a["irr"], adj_lo=a["lo"], adj_hi=a["hi"], adj_p=a["p"])


def definition_sensitivity(tm):
    rows = [_row(tm, k, lab, k) for k, lab in DEF_LABEL.items()]
    for key, lab, mask in (("S1", "S1 Excluding partial 2026-27 season", tm.season != "2026-27"),
                           ("S2", "S2 2023-24 onward (ESPN labels overturns explicitly)", tm.season >= "2023-24"),
                           ("S3", "S3 Top-10 final-table teams only", tm.top10 == True)):  # noqa: E712
        rows.append(_row(tm[mask], "D0", lab, key))
    return pd.DataFrame(rows)


def estimator_sensitivity(tm):
    rows = []
    for lab, kw in (("Poisson, SE clustered by match (primary)", {}),
                    ("Poisson, SE clustered by team-season", dict(cluster=team_season_groups)),
                    ("Poisson without offsides as a control", dict(rhs="is_rm + l_shots + xg_ + home + C(season)")),
                    ("Poisson with shots on target instead of shots", dict(rhs="is_rm + l_off + np.log1p(sot) + xg_ + home + C(season)"))):
        a = fit_irr(tm, "D0", **kw)
        rows.append((lab, a["irr"], a["lo"], a["hi"]))
    t = tm.dropna(subset=["shots", "offsides", "xg", "sot"])
    m = smf.negativebinomial(f"D0 ~ {ADJ}", t).fit(disp=0, maxiter=300)
    b, se = m.params["is_rm"], m.bse["is_rm"]
    rows.append((f"Negative binomial (alpha = {m.params['alpha']:.2f})", np.exp(b), np.exp(b - 1.96 * se), np.exp(b + 1.96 * se)))
    return pd.DataFrame(rows, columns=["estimator", "irr", "lo", "hi"])


def leave_one_season_out(tm):
    rows = []
    for s in sorted(tm.season.unique()):
        t = tm[tm.season != s]
        a = fit_irr(t, "D0")
        rows.append(dict(dropped_season=s, rm_events=int(t[t.is_rm == 1].D0.sum()), irr=a["irr"], lo=a["lo"], hi=a["hi"]))
    return pd.DataFrame(rows)


def club_effects(tm, min_matches=100):
    """Adjusted IRR of each club versus the clubs other than Real Madrid (same model as the Real Madrid estimate)."""
    base = tm[tm.team != RM]
    rows = []
    for team, n in tm.groupby("team").size().items():
        if n < min_matches:
            continue
        t = (tm if team == RM else base).copy()
        t["is_c"] = (t.team == team).astype(int)
        a = fit_irr(t, "D0", term="is_c", rhs=ADJ.replace("is_rm", "is_c"))
        rows.append(dict(team=team, matches=int(n), events=int(tm[tm.team == team].D0.sum()), irr=a["irr"], lo=a["lo"], hi=a["hi"], p=a["p"]))
    out = pd.DataFrame(rows).sort_values("irr", ascending=False).reset_index(drop=True)
    out["rank"] = out.index + 1
    return out


def classification_mix(d):
    """Does the evidence quality / reason mix of Real Madrid's events differ from other clubs' events?"""
    x = d[d.var_confirmed]
    is_rm = x.team == RM
    rows = []

    def add(item, mask, sub=None):
        s = x if sub is None else x[sub]
        r = s.team == RM
        a, na, b, nb = int(mask[s.index][r].sum()), int(r.sum()), int(mask[s.index][~r].sum()), int((~r).sum())
        rows.append(dict(item=item, rm=a, rm_n=na, rm_pct=100 * a / na, others=b, others_n=nb, others_pct=100 * b / nb,
                         fisher_p=stats.fisher_exact([[a, na - a], [b, nb - b]])[1]))

    for t in sorted(x.tier.unique()):
        add(t, x.tier == t)
    add("ESPN review-type event within 3 min, all seasons", x.espn_ok)
    add("ESPN review-type event within 3 min, 2023-24 onward", x.espn_ok, x.season >= "2023-24")
    for r in ("offside", "Foul", "handball", "video review"):
        add(f"Reason: {r}", x.reason_fs == r)
    return pd.DataFrame(rows)


def referee_heterogeneity(tm, mt, n_sim=5000):
    """Chi-square homogeneity of Real Madrid's rate across referees (>= 8 RM matches) and its power."""
    rng = np.random.default_rng(SEED)
    t = tm[tm.is_rm == 1].assign(referee=lambda x: x.fs_id.map(mt.set_index("fs_id").referee))
    g = t.groupby("referee").agg(m=("fs_id", "size"), e=("D0", "sum"))
    g = g[g.m >= 8]
    lam = g.e.sum() / g.m.sum()
    chi = (((g.e - lam * g.m) ** 2) / (lam * g.m)).sum()
    out = [dict(item="Observed chi-square", value=chi, detail=f"{len(g) - 1} d.f., p = {1 - stats.chi2.cdf(chi, len(g) - 1):.2f}; "
                                                              f"{len(g)} referees, {int(g.m.sum())} matches, {int(g.e.sum())} events")]
    for sd in (0.25, 0.5, 0.75, 1.0):
        rej = 0
        for _ in range(n_sim):
            true = lam * np.exp(sd * rng.standard_normal(len(g)) - sd ** 2 / 2)
            y = rng.poisson(true * g.m.to_numpy())
            lh = y.sum() / g.m.sum()
            rej += (((y - lh * g.m.to_numpy()) ** 2) / (lh * g.m.to_numpy())).sum() > stats.chi2.ppf(0.95, len(g) - 1)
        out.append(dict(item=f"Power at 5% level if true referee rates vary log-normally, SD {sd}", value=rej / n_sim,
                        detail="share of simulated datasets with p < 0.05"))
    return pd.DataFrame(out)


def post_comparison(d):
    """Our counts for the clubs listed in the 10-Oct-2026 post (events before that day)."""
    post = {"Real Madrid": 42, "Atl\u00e9tico de Madrid": 22, "Villarreal": 22, "Celta de Vigo": 20, "Real Sociedad": 20, "Sevilla": 20,
            "FC Barcelona": 19}
    x = d[d.var_confirmed & (d.kickoff < "2026-10-10")]
    rows = []
    for t, n in post.items():
        rows.append(dict(team=t, post=n, primary_definition=int((x.team == t).sum()),
                         offside_plus_foul=int(((x.team == t) & x.reason_fs.isin(["offside", "Foul"])).sum()),
                         offside_only=int(((x.team == t) & (x.reason_fs == "offside")).sum())))
    return pd.DataFrame(rows)


def audit_power(n_rm=50, n_comp=131):
    """Power of the planned audit to detect a lower share of valid events in one group (normal approximation)."""
    from statsmodels.stats.power import NormalIndPower
    from statsmodels.stats.proportion import proportion_effectsize
    rows = []
    for p1, p2 in ((0.95, 0.85), (0.95, 0.80), (0.95, 0.70)):
        pw = NormalIndPower().solve_power(effect_size=proportion_effectsize(p1, p2), nobs1=n_rm, ratio=n_comp / n_rm, alpha=0.05)
        rows.append(dict(valid_share_group_1=p1, valid_share_group_2=p2, n_rm=n_rm, n_comparison=n_comp, power=pw))
    return pd.DataFrame(rows)


def audit_files(ev, seed=SEED):
    """Key + blank form for re-reviewing every incident (Real Madrid and comparison clubs) with one protocol."""
    top = ev.team.value_counts().index[:6]  # Real Madrid + the five comparison clubs with most events
    k = ev.assign(priority=np.where(ev.team.isin(top), 1, 2)).sample(frac=1, random_state=seed).reset_index(drop=True)
    k["audit_id"] = [f"A{i + 1:03d}" for i in range(len(k))]
    key = k[["audit_id", "priority", "season", "fs_id", "date", "team", "opponent", "minute_num", "player_full", "reason_fs", "tier"]]
    form_cols = ["initial_onfield_decision", "var_action", "final_decision", "final_reason", "event_meets_protocol", "subtype",
                 "reviewer_id", "video_source", "second_reviewer_meets_protocol", "second_reviewer_subtype", "disagreement_resolution", "notes"]
    form = key[["audit_id", "date", "minute_num"]].copy()
    for c in form_cols:
        form[c] = ""
    return key, form


def ascertainment_bias(h):
    """Deterministic what-if: rescale the adjusted IRR for assumed differential recording. Not estimates."""
    rows = []
    for c in (1.0, 1.25, 1.45, 1.5, 2.0):
        rows.append(dict(scenario=f"Other clubs' true events are {c:g}x the recorded ones", assumption=c,
                         irr=h["irr_adj"] / c, lo=h["irr_adj_lo"] / c, hi=h["irr_adj_hi"] / c))
    n = h["rm_events"]
    for k in (0, 5, 10, 15, 20, 25):
        f = (n - k) / n
        rows.append(dict(scenario=f"{k} of Real Madrid's {n} events are not true overturns", assumption=k,
                         irr=h["irr_adj"] * f, lo=h["irr_adj_lo"] * f, hi=h["irr_adj_hi"] * f))
    return pd.DataFrame(rows)

# --------------------------------------------------------------------------- title fixed-score scenarios


def season_champion(home, away, hg, ag, n_teams):
    """Champion under La Liga tie-breaks: points, then head-to-head points / goal difference, then GD, then GF."""
    hp = np.where(hg > ag, 3, np.where(hg == ag, 1, 0))
    ap = np.where(ag > hg, 3, np.where(hg == ag, 1, 0))
    pts, gd, gf = (np.zeros(n_teams) for _ in range(3))
    for arr, a, b, c in ((pts, hp, ap, None), (gd, hg - ag, ag - hg, None), (gf, hg, ag, None)):
        np.add.at(arr, home, a)
        np.add.at(arr, away, b)
    top = np.flatnonzero(pts == pts.max())
    if len(top) == 1:
        return int(top[0]), pts
    s = set(top.tolist())
    sel = np.array([h in s and a in s for h, a in zip(home, away)])
    h2p, h2g = np.zeros(n_teams), np.zeros(n_teams)
    np.add.at(h2p, home[sel], hp[sel])
    np.add.at(h2p, away[sel], ap[sel])
    np.add.at(h2g, home[sel], (hg - ag)[sel])
    np.add.at(h2g, away[sel], (ag - hg)[sel])
    best = sorted(top, key=lambda i: (h2p[i], h2g[i], gd[i], gf[i]), reverse=True)[0]
    return int(best), pts


def title_scenarios(d, res, n_sim=20000):
    """Fixed-score scenario (all RM goals restored, all other scoring unchanged) and assumed-error Monte-Carlo."""
    rng = np.random.default_rng(SEED)
    x = d[(d.team == RM) & d.var_confirmed]
    rows, mc = [], []
    for season, g in res.groupby("season"):
        if len(g) < 380:
            continue
        g = g.reset_index(drop=True)
        teams = sorted(set(g.home) | set(g.away))
        idx = {t: i for i, t in enumerate(teams)}
        home, away = g.home.map(idx).to_numpy(), g.away.map(idx).to_numpy()
        hg, ag = g.home_goals.to_numpy(), g.away_goals.to_numpy()
        pos = {f: i for i, f in enumerate(g.fs_id)}
        ev = x[x.season == season]
        add_h, add_a = np.zeros(len(g), int), np.zeros(len(g), int)
        for f, n in ev.groupby("fs_id").size().items():
            (add_h if g.home.iloc[pos[f]] == RM else add_a)[pos[f]] = n
        c0, p0 = season_champion(home, away, hg, ag, len(teams))
        cA, pA = season_champion(home, away, hg + add_h, ag + add_a, len(teams))
        r = idx[RM]
        rows.append(dict(season=season, rm_events=int(len(ev)), champion_actual=teams[c0], rm_pts_actual=int(p0[r]),
                         best_other_pts_actual=int(np.delete(p0, r).max()), champion_if_all_restored=teams[cA],
                         rm_pts_if_all_restored=int(pA[r]), best_other_pts_if_all_restored=int(np.delete(pA, r).max()),
                         champion_changes=c0 != cA))
        if teams[c0] == RM or len(ev) == 0:
            continue
        goals = [(pos[f], g.home.iloc[pos[f]] == RM) for f in ev.fs_id]
        cache = {}
        for p in (0.017, 0.05, 0.10, 0.25, 0.50):
            wins = 0
            for fl in rng.random((n_sim, len(goals))) < p:
                ah, aa = np.zeros(len(g), int), np.zeros(len(g), int)
                for (i, is_home), f in zip(goals, fl):
                    if f:
                        (ah if is_home else aa)[i] += 1
                key = (ah.tobytes(), aa.tobytes())
                if key not in cache:
                    cache[key] = season_champion(home, away, hg + ah, ag + aa, len(teams))[0] == r
                wins += cache[key]
            mc.append(dict(season=season, assumed_error_probability=p, p_rm_champion=wins / n_sim))
    return pd.DataFrame(rows), pd.DataFrame(mc)

# --------------------------------------------------------------------------- driver


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tm, d, onf, res = load()
    d = classify_events(d)
    tm, _ = build_panel(tm, d, onf)
    H = headline(tm)
    S = var_stage(tm)
    H.update(var_extra_irr=S["var_extra"]["irr"], var_extra_lo=S["var_extra"]["lo"], var_extra_hi=S["var_extra"]["hi"],
             var_extra_p=S["var_extra"]["p"], onfield_irr_adj=S["onfield"]["irr"])
    tables = {
        "definition_sensitivity": definition_sensitivity(tm),
        "estimator_sensitivity": estimator_sensitivity(tm),
        "leave_one_season_out": leave_one_season_out(tm),
        "club_adjusted_effects": club_effects(tm),
        "classification_mix": classification_mix(d),
        "ascertainment_what_if": ascertainment_bias(H),
    }
    tables["title_fixed_score_scenario"], tables["title_assumed_error_scenarios"] = title_scenarios(d, res)
    ev = d[d.var_confirmed][["season", "fs_id", "date", "team", "opponent", "venue", "player_full", "minute_num", "reason_fs",
                              "tier", "espn_ok", "text_var", "referee_full"]]
    tables["events_with_evidence_tier"] = ev
    tables["referee_heterogeneity"] = referee_heterogeneity(tm, pd.read_csv(P / "matches_ref.csv"))
    tables["post_vs_reconstruction"] = post_comparison(d)
    tables["audit_power"] = audit_power(int((ev.team == RM).sum()), int(ev.team.isin(ev.team.value_counts().index[1:6]).sum()))
    key, form = audit_files(ev)
    tables["manual_audit_key"], tables["manual_audit_form"] = key, form
    for name, df in tables.items():
        df.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8-sig")
    (OUT / "headline.json").write_text(json.dumps({k: (v if isinstance(v, (str, int)) else float(v)) for k, v in H.items()}, indent=1),
                                       encoding="utf-8")
    pd.set_option("display.width", 220, "display.max_columns", 30, "display.max_colwidth", 70)
    print(json.dumps({k: round(v, 3) if isinstance(v, float) else v for k, v in H.items()}, indent=1))
    for name, df in tables.items():
        if name not in ("events_with_evidence_tier", "manual_audit_key", "manual_audit_form"):
            print("\n==", name)
            print(df.round(3).to_string())


if __name__ == "__main__":
    main()
