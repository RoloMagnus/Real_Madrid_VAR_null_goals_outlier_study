"""Build the Excel report from data/processed/analysis.pkl -> Real Madrid VAR Nullified Goals Analysis.xlsx"""
import os
import pickle
import re

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "data", "processed")
XLSX = os.path.join(ROOT, "Real Madrid VAR Nullified Goals - Analysis.xlsx")
RM = "Real Madrid"
O = pickle.load(open(os.path.join(P, "analysis.pkl"), "rb"))
tm, d, mt, ft, ts = O["tm"], O["d"], O["mt"], O["ft"], O["ts"]

# ------------------------------------------------------------------ core tables
d = d.copy()
d["round_no"] = d.fs_id.map(mt.set_index("fs_id")["round"]).str.extract(r"(\d+)")[0].astype(float)
champ = ft[ft.final_pos == 1].set_index("season").team
d["champion"] = d.season.map(champ)
d.loc[d.season == "2026-27", "champion"] = d.loc[d.season == "2026-27", "champion"].map(lambda x: f"In progress (leader: {x})")
d["kickoff"] = pd.to_datetime(d.kickoff)
d = d.sort_values("kickoff").reset_index(drop=True)
vd = d[d.var_confirmed].copy()  # primary definition: VAR-attributed
n_all, n_var = len(d), len(vd)


def outcome(gf, ga):
    return "WIN" if gf > ga else "DRAW" if gf == ga else "LOSS"


def build_breakdown(x):
    out = pd.DataFrame({
        "rank": range(1, len(x) + 1),
        "date": x.kickoff.dt.normalize(),
        "season": x.season.str.replace(r"(\d{4})-(\d{2})", lambda m: f"{m.group(1)}-20{m.group(2)}", regex=True),
        "round": x.round_no,
        "team (goal nullified)": x.team,
        "rival": x.opponent,
        "active_player": x.player_full,
        "passive_player": x.offside_player_espn.where(x.category == "Offside - teammate in build-up"),
        "local_flag": x.venue.eq("Home"),
        "var_reason": x.reason_fs.map({"offside": "Offside", "Foul": "Foul", "handball": "Handball", "video review": "Video review (unspecified)"}),
        "context_category": x.category,
        "minute": x.minute_num,
        "minute_display": x.minute,
        "half": x.half_label.map({"1st half": "first", "2nd half": "second"}),
        "score_before_goal (team-opp)": [f"{a}-{b}" if v == "Home" else f"{b}-{a}" for a, b, v in zip(x.score_home, x.score_away, x.venue)],
        "what_the_goal_would_have_been": x.goal_effect,
        "team_goals_final": x.team_gf,
        "rival_goals_final": x.team_ga,
        "outcome": [outcome(a, b) for a, b in zip(x.team_gf, x.team_ga)],
        "points_lost_due_to_nullification": x.points_lost,
        "league_position_at_time": x.pos_before,
        "rival_position_at_time": x.opp_pos_before,
        "points_at_time": x.pts_before,
        "referee_on_field": x.referee_full,
        "laliga_title_won_flag": [c == t for c, t in zip(x.champion, x.team)],
        "la_liga_champion": x.champion,
        "var_decision_text": x.context_text,
        "var_evidence": ["Explicit VAR wording / ESPN review" if v else "Flashscore incident only" for v in x.var_confirmed],
    })
    return out


RM_B = build_breakdown(vd[vd.team == RM])
ALL_B = build_breakdown(vd)

# manual validation flag + video link, taken from the user's validated file (matched on date, player and minute)
VALIDATED = os.path.join(ROOT, "RM_nullified_goals_breakdown_validated.xlsx")
HAVE_VALID = os.path.exists(VALIDATED)
if HAVE_VALID:
    _sheet = next(s for s in pd.ExcelFile(VALIDATED).sheet_names if s.startswith("RM_") and "breakdown" in s)
    _v = pd.read_excel(VALIDATED, sheet_name=_sheet)
    _v["k"] = pd.to_datetime(_v.date).dt.date.astype(str) + "|" + _v.active_player.astype(str) + "|" + _v.minute.astype(str)
    RM_B["_k"] = RM_B.date.dt.date.astype(str) + "|" + RM_B.active_player.astype(str) + "|" + RM_B.minute.astype(str)
    _m = _v.drop_duplicates("k").set_index("k")
    RM_B["manual_validation"] = RM_B._k.map(_m.manual_validation)
    RM_B["links"] = RM_B._k.map(_m.links)
    RM_B = RM_B.drop(columns="_k")
    print("validated rows matched:", int(RM_B.manual_validation.notna().sum()), "of", len(RM_B), "| validated file rows:", len(_v))

# ------------------------------------------------------------------ derived summaries
team_counts = vd.team.value_counts()
team_tbl = pd.crosstab(vd.team, vd.reason_fs).reindex(columns=["offside", "Foul", "handball", "video review"], fill_value=0)
team_tbl["Total"] = team_tbl.sum(axis=1)
mp = tm.groupby("team").size().rename("matches_played")
team_tbl = team_tbl.join(mp)
team_tbl["per_match"] = team_tbl.Total / team_tbl.matches_played
gf = tm.groupby("team").gf.sum().rename("goals")
team_tbl = team_tbl.join(gf)
team_tbl["per_100_goal_events"] = 100 * team_tbl.Total / (team_tbl.goals + team_tbl.Total)
team_tbl["rank"] = team_tbl.Total.rank(ascending=False, method="min").astype(int)
team_tbl = team_tbl.sort_values("Total", ascending=False).reset_index().rename(columns={"index": "team", "team": "team"})
team_tbl.columns = ["Team", "Offside", "Attacking foul", "Handball", "Video review (unspecified)", "Total", "Matches played",
                    "Nullified / match", "Goals scored", "Nullified per 100 goal events", "Rank"]
team_tbl = team_tbl[["Rank", "Team", "Total", "Offside", "Attacking foul", "Handball", "Video review (unspecified)", "Matches played",
                     "Nullified / match", "Goals scored", "Nullified per 100 goal events"]]
season_mat = pd.crosstab(vd.team, vd.season).reindex(team_tbl.Team)
season_mat["Total"] = season_mat.sum(axis=1)
season_mat = season_mat.reset_index().rename(columns={"team": "Team"})

rm_ts = ts[ts.team == RM].set_index("season")
oth10 = ts[(ts.team != RM) & ts.top10].groupby("season").agg(dis=("dis", "sum"), n=("team", "size"), matches=("matches", "sum"))
season_cmp = pd.DataFrame({"season": rm_ts.index, "RM nullified": rm_ts.dis.values,
                           "RM nullified per 38 matches": (rm_ts.dis / rm_ts.matches * 38).values,
                           "Avg other top-10 team (per 38 matches)": (oth10.dis / oth10.matches * 38).reindex(rm_ts.index).values,
                           "RM goals": rm_ts.goals.values, "RM shots": rm_ts.shots.values, "RM xG": rm_ts.xg.round(1).values,
                           "RM offsides": rm_ts.offsides.values, "RM final position": rm_ts.final_pos.values})

# RM EDA tables
r = vd[vd.team == RM].copy()
r["minute_bin"] = pd.cut(r.minute_num.clip(upper=95), [0, 15, 30, 45, 60, 75, 90, 200], labels=["1-15", "16-30", "31-45(+)", "46-60", "61-75", "76-90", "90+"], right=True)
r.loc[(r.half == 1) & (r.minute_num > 45), "minute_bin"] = "31-45(+)"
r.loc[(r.half == 2) & (r.minute_num <= 45), "minute_bin"] = "46-60"
def vc(s, name):
    x = s.value_counts().rename_axis(name).reset_index(name="RM nullified goals")
    x["% of total"] = 100 * x["RM nullified goals"] / x["RM nullified goals"].sum()
    return x
eda = {
    "By reason (Flashscore)": vc(r.reason_fs.map({"offside": "Offside", "Foul": "Attacking foul", "handball": "Handball", "video review": "Video review (unspecified)"}), "Reason"),
    "By context category": vc(r.category, "Category"),
    "By half": vc(r.half_label, "Half"),
    "By 15-minute window": vc(r.minute_bin.astype(str), "Minute window").sort_values("Minute window"),
    "By venue": vc(r.venue, "Venue"),
    "By what the goal would have meant": vc(r.goal_effect, "Goal effect"),
    "By RM league position at the time": vc(r.pos_before.map(lambda v: "n/a (round 1)" if pd.isna(v) else f"P{int(v)}"), "RM position").sort_values("RM position"),
    "By match outcome": vc(pd.Series([outcome(a, b) for a, b in zip(r.team_gf, r.team_ga)], index=r.index), "Final outcome"),
    "Top players (goal scorer)": vc(r.player_full, "Player").head(12),
    "Top rivals": vc(r.opponent, "Rival").head(12),
}
cl = O["cluster"]
rate = O["rate_tests"]; glm = O["glm"]; fc = O["forecast"]; sym = O["symmetry"]; fav = O["fav"]
ref = O["ref"]; rmeta = O["ref_meta"]; acc = O["acc"]; corr = O["corr"]; agg = O["top10_agg"]; ledger = O["ledger"]
pg, pcf, pfc, ppr = O["ppda_glm"], O["ppda_coef"], O["ppda_fc"], O["ppda_profile"]
dg, dcf, dfc, dpr, rrt = O["disc_glm"], O["disc_coef"], O["disc_fc"], O["disc_profile"], O["reason_rates"]
onr, ong, ont, oni = O["onf_rates"], O["onf_glm"], O["onf_teams"], O["onf_inter"]
onf_ev = pd.read_csv(os.path.join(P, "onfield_disallowed_events.csv"), parse_dates=["date"])

# ---- exports from the EDA notebook (player concentration, matches affected, champion vs not, title scenarios)
FIGD = os.path.join(ROOT, "figures")
EDA_FILES = {n: os.path.join(P, f"eda_{n}.csv") for n in ("player_concentration", "rm_matches_with_nullified", "champion_vs_not", "title_scenarios",
                                                          "title_break_even", "title_monte_carlo", "title_leaderboards")}
HAVE_EDA = all(os.path.exists(p) for p in EDA_FILES.values())
if HAVE_EDA:
    e_pc = pd.read_csv(EDA_FILES["player_concentration"], index_col=0).iloc[:, 0]
    e_g = pd.read_csv(EDA_FILES["rm_matches_with_nullified"], parse_dates=["date"])
    e_ss = pd.read_csv(EDA_FILES["champion_vs_not"])
    e_sc = pd.read_csv(EDA_FILES["title_scenarios"])
    e_be = pd.read_csv(EDA_FILES["title_break_even"])
    e_mc = pd.read_csv(EDA_FILES["title_monte_carlo"])
    e_lb = pd.read_csv(EDA_FILES["title_leaderboards"])
    e_cum = e_pc.cumsum() / e_pc.sum()
    e_k75 = int((e_cum < 0.75).sum() + 1)
    e_dl = int((e_g.outcome != "WIN").sum())
    e_chg = int((e_g.result_change != "No change").sum())
    e_pts = int(e_g.points_lost.sum())
    e_grp = e_ss.groupby("status").agg(seasons=("season", "size"), matches=("matches", "sum"), nullified=("nullified", "sum"),
                                       points_lost=("points_lost_if_counted", "sum"), matches_with_nullified=("matches_with_nullified", "sum"))
    e_a = e_sc[e_sc.scenario.str.startswith("A.") & (e_sc.season != "2026-27")]
    e_changed = list(e_a[e_a.title_changed].season)
onr_all = onr[(onr.scope == "All 20 teams per season") & (onr.exposure == "per match played")]
on_rm = onr_all[onr_all.category.str.startswith("On-field")].iloc[0]
cb_rm = onr_all[onr_all.category.str.startswith("Combined")].iloc[0]
on_int = oni[(oni.scope == "All 20 teams per season") & oni.model.str.startswith("Controlled") & oni.term.str.startswith("Extra")].iloc[0]
on_glm_c = ong[(ong.scope == "All 20 teams per season") & ong.category.str.startswith("On-field") & ong.model.str.startswith("+")].iloc[0]
on_tot, on_rm_n = len(onf_ev), int((onf_ev.team == RM).sum())
dg_ref = dg[(dg.scope == "All 20 teams per season") & dg.model.str.startswith("Reference")].iloc[0]
dg_full = dg[(dg.scope == "All 20 teams per season") & dg.model.str.startswith("Full")].iloc[0]
dg_full10 = dg[(dg.scope == "Top-10 teams per season") & dg.model.str.startswith("Full")].iloc[0]
df_all = dfc[dfc.scope == "All 20 teams per season"].iloc[0]
dp_rm = dpr[(dpr.scope == "Top-10 teams per season") & (dpr.group == "Real Madrid")].iloc[0]
dp_ot = dpr[(dpr.scope == "Top-10 teams per season") & (dpr.group == "Other teams")].iloc[0]
rs_off = rrt[(rrt.scope == "All 20 teams per season") & (rrt.reason == "Offside")].iloc[0]
rs_fou = rrt[(rrt.scope == "All 20 teams per season") & (rrt.reason == "Attacking foul")].iloc[0]
pg_ref = pg[(pg.scope == "All 20 teams per season") & pg.model.str.startswith("Reference")].iloc[0]
pg_full = pg[(pg.scope == "All 20 teams per season") & pg.model.str.startswith("+ own and opponent")].iloc[0]
pg_full10 = pg[(pg.scope == "Top-10 teams per season") & pg.model.str.startswith("+ own and opponent")].iloc[0]
pf_all = pfc[pfc.scope == "All 20 teams per season"].iloc[0]
pp_rm = ppr[(ppr.scope == "Top-10 teams per season") & (ppr.group == "Real Madrid")].iloc[0]
pp_ot = ppr[(ppr.scope == "Top-10 teams per season") & (ppr.group == "Other teams")].iloc[0]
tw = O["tweet_val"]; espn = O["espn_check"]; sv = O["stat_validation"]

# headline numbers for the narrative
rm_n = int(team_counts[RM]); second = team_counts.drop(RM).idxmax(); second_n = int(team_counts.drop(RM).max())
before_today = int(((vd.team == RM) & (vd.kickoff < pd.Timestamp("2026-10-10"))).sum())
g = lambda sc, ex: rate[(rate.scope == sc) & (rate.exposure == ex)].iloc[0]
a20, t10 = "All 20 teams per season", "Top-10 teams per season (final table)"
rr_match = g(a20, "per match played"); rr_shots = g(a20, "per 100 shots"); rr_off = g(a20, "per 100 offsides")
rr_ge = g(a20, "per 100 goal events (goals + nullified)")
m_full = glm[(glm.scope == "All 20 teams per season") & glm.model.str.startswith("M6")].iloc[0]
m_raw = glm[(glm.scope == "All 20 teams per season") & glm.model.str.startswith("M0")].iloc[0]
m_t10 = glm[(glm.scope == "Top-10 teams per season") & glm.model.str.startswith("M6")].iloc[0]
f_all = fc[(fc.scope == "All 20 teams per season") & (fc.model_trained_on_other_teams == "offsides + shots + xG")].iloc[0]
f_t10 = fc[(fc.scope == "Top-10 teams per season") & (fc.model_trained_on_other_teams == "offsides + shots + xG")].iloc[0]
s_off = sym.iloc[0]; s_shots = sym.iloc[1]; s_xg = sym.iloc[2]; s_go = sym.iloc[3]
f_pm = fav.iloc[0]; f_po = fav.iloc[1]
led_rm = ledger[ledger.team == RM].iloc[0]
cr = lambda scope, y: corr[(corr.scope == scope) & (corr.y == y)].iloc[0]
c_sh = cr("Top-10 team-seasons, 8 full seasons (counts)", "Shots (chances created)")
c_xg = cr("Top-10 team-seasons, 8 full seasons (counts)", "xG")
c_of = cr("Top-10 team-seasons, 8 full seasons (counts)", "Offsides (attacking positions)")
c_of_pm = cr("Top-10 team-seasons, 9 seasons incl. 2026-27 (per match)", "Offsides (attacking positions) / match")
rm_row = agg[agg.team == RM].iloc[0]
bar_row = agg[agg.team == "FC Barcelona"].iloc[0]

# ------------------------------------------------------------------ workbook
with pd.ExcelWriter(XLSX, engine="xlsxwriter", datetime_format="yyyy-mm-dd", engine_kwargs={"options": {"nan_inf_to_errors": True}}) as xw:
    wb = xw.book
    ORDER = ["Summary", "1_Tweet_Validation", "2_RM_Nullified_Goals", "3_All_Teams_Nullified", "4_Team_Ranking", "5_Attack_Volume_Top10",
             "6_Stat_Framework", "7_RM_EDA", "8_Referees", "9_Net_Points_Ledger", "10_VAR_Accuracy_Refs", "11_Sources_Method_Limits", "12_OnField_Disallowed", "13_Titles_Players_Games"]
    for _n in ORDER:
        wb.add_worksheet(_n)
    wb.add_worksheet = lambda name: wb.get_worksheet_by_name(name)  # sheets already exist in the desired order
    F = lambda **k: wb.add_format({"font_name": "Calibri", "font_size": 10, **k})
    f_title = F(bold=True, font_size=16, font_color="#1F3864")
    f_h2 = F(bold=True, font_size=12, font_color="#FFFFFF", bg_color="#1F3864")
    f_h3 = F(bold=True, font_size=11, font_color="#1F3864", bottom=1)
    f_hdr = F(bold=True, bg_color="#D9E1F2", border=1, text_wrap=True, valign="vcenter")
    f_txt = F(text_wrap=True, valign="top")
    f_note = F(italic=True, font_color="#595959", text_wrap=True, valign="top")
    f_good = F(bg_color="#E2EFDA", text_wrap=True, valign="top", border=1)
    f_warn = F(bg_color="#FFF2CC", text_wrap=True, valign="top", border=1)
    f_bad = F(bg_color="#FCE4D6", text_wrap=True, valign="top", border=1)
    f_rm = F(bg_color="#FFF2CC", bold=True)
    f2 = F(num_format="0.00"); f3 = F(num_format="0.000"); f1 = F(num_format="0.0"); f0 = F(num_format="0"); fp = F(num_format="0.0")
    fdate = F(num_format="yyyy-mm-dd")
    fpv = F(num_format="0.0000")

    def put_df(ws, df, r0, c0=0, fmts=None, hdr=True, widths=None, rm_col=None):
        fmts = fmts or {}
        if hdr:
            for j, c in enumerate(df.columns):
                ws.write(r0, c0 + j, str(c), f_hdr)
        for i, row in enumerate(df.itertuples(index=False), start=r0 + (1 if hdr else 0)):
            for j, v in enumerate(row):
                col = df.columns[j]
                fm = fmts.get(col)
                if isinstance(v, (pd.Timestamp,)) and not pd.isna(v):
                    ws.write_datetime(i, c0 + j, v.to_pydatetime(), fdate)
                elif v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NaT:
                    ws.write_blank(i, c0 + j, None)
                elif isinstance(v, (bool, np.bool_)):
                    ws.write_boolean(i, c0 + j, bool(v))
                elif isinstance(v, (int, float, np.integer, np.floating)):
                    ws.write_number(i, c0 + j, float(v), fm)
                else:
                    ws.write(i, c0 + j, str(v), fm)
        return r0 + len(df) + (1 if hdr else 0)

    # ============================================================ Summary
    ws = wb.add_worksheet("Summary"); xw.sheets["Summary"] = ws
    ws.hide_gridlines(2); ws.set_column(0, 0, 3); ws.set_column(1, 1, 34); ws.set_column(2, 2, 120)
    ws.write(0, 1, "Real Madrid & VAR-nullified goals in La Liga (2018-19 to 12 Oct 2026) - validation, breakdown and statistical test", f_title)
    ws.write(1, 1, "Prepared 12 Oct 2026. Data window: every La Liga match from 2018-19 (VAR introduced) to 12-Oct-2026 (3,118 matches, 2026-27 season partial).", f_note)
    rows = [
        ("I. Validation of MisterChip's table", "", None),
        ("Direction of the claim", f"CONFIRMED. Real Madrid is #1 by a wide margin in the reconstructed data: {rm_n} nullified goals ({before_today} before the 10-Oct-2026 match + 1 on the day) vs {second} for the runner-up ({second_n}). The independent ESPN log (2023-24 onwards) also ranks Real Madrid #1 with the same share (12.7% ESPN vs 12.2% Flashscore).", f_good),
        ("Exact numbers", f"NOT REPRODUCIBLE. The tweet shows RM 42 (+1); the reconstruction gives {before_today} before the Vinicius goal (+1 = {rm_n}). All 7 teams in the tweet are 5-42% higher in the reconstruction (Villarreal 30 vs 22, Barcelona 27 vs 19). A narrower definition (offside + attacking-foul only) reproduces RM 42, Atletico 22, Celta 20 exactly but not the other teams, so the source/definition behind the post is unknown. The gap RM vs #2 is {rm_n/second_n:.2f}x here vs 1.91x in the post.", f_warn),
        ("Your 4-row validation sample", "Row 1 (Sevilla) correct (minute 54 in our feed vs 53 in yours). Row 2 (Levante): minute is 18, not 43 (43' is a Levante offside in ESPN). Row 3 (Valencia, 1-Dec-2018): NOT FOUND in Flashscore or ESPN - no VAR review at that match; likely not a VAR nullification. Row 4 mixes two matches: the Modric/Varane offside is the Celta match of 16-Mar-2019 (56', 2-0 home win, ref Martinez Munuera); the 10-Mar Valladolid match only had a Valladolid goal ruled out. Details in sheet 1.", f_warn),
        ("II. Breakdown", "", None),
        ("Sheet 2_RM_Nullified_Goals", f"{rm_n} Real Madrid goals, one row per goal, with your column layout (rank, date, season, round, rival, active/passive player, local_flag, var_reason, title flag, champion, scores, minute, half, outcome, referee) plus: league position at the time, rival position, score before the goal, what the goal would have meant, points lost, VAR decision text. Referee = on-field referee (formal decision-maker after VAR advice); the VAR-room official is not published consistently by any source I could reach.", f_txt),
        ("III. Is Real Madrid being targeted?", "", None),
        ("Raw outlier", f"Real Madrid has {rr_match.rm_rate:.3f} nullified goals per match vs {rr_match.others_rate:.3f} for everyone else = {rr_match.rate_ratio:.1f}x (95% CI {rr_match.rr_ci_low:.1f}-{rr_match.rr_ci_high:.1f}, p<0.0001). It is a real statistical outlier, not noise.", f_txt),
        ("How much is attacking volume?", f"Partly. Controlling for shots, offsides and xG (Poisson regression, 6,160 team-matches) the Real Madrid effect falls from {m_raw.rm_irr:.2f}x to {m_full.rm_irr:.2f}x (95% CI {m_full.irr_ci_low:.2f}-{m_full.irr_ci_high:.2f}); top-10 only: {m_t10.rm_irr:.2f}x. A model trained on the other teams predicts ~{f_all.rm_expected:.0f} nullified goals for Real Madrid (95% interval {f_all.expected_p2_5:.0f}-{f_all.expected_p97_5:.0f}) vs {int(f_all.rm_observed)} observed. So volume explains roughly half the count; about 2x remains unexplained. Barcelona has almost the same attack volume (shots {bar_row.shots_pm:.1f} vs {rm_row.shots_pm:.1f} per match, offsides {bar_row.offsides_pm:.2f} vs {rm_row.offsides_pm:.2f}) but 27 nullified goals vs {rm_n}.", f_warn),
        ("Correlations (top-10, addendum item 3)", f"Nullified goals vs chances created: shots r={c_sh.pearson_r:.2f} (95% CI {c_sh.pearson_ci_low:.2f}-{c_sh.pearson_ci_high:.2f}), xG r={c_xg.pearson_r:.2f}: moderate and significant. vs offsides in attack: r={c_of.pearson_r:.2f} (p={c_of.pearson_p:.3f}; per-match r={c_of_pm.pearson_r:.2f}, p={c_of_pm.pearson_p:.2f}): weak. The two best-known drivers (attack volume, offside volume) correlate with the count, but Real Madrid sits well above the fitted line.", f_txt),
        ("Evidence for external bias / favouritism", f"NOT SUPPORTED by the available data. (1) Same-match test: in Real Madrid matches the split of nullified goals (RM {int(s_off.nullified_rm)} vs opponents {int(s_off.nullified_opponents)}) is what Real Madrid's share of offsides predicts (expected {s_off.expected_rm:.0f}, 95% {s_off.expected_p2_5:.0f}-{s_off.expected_p97_5:.0f}, p={s_off.p_value_rm_obs_or_more:.2f}) and of goal opportunities (p={s_go.p_value_rm_obs_or_more:.2f}); under shots/xG shares RM is somewhat above expectation (p={s_shots.p_value_rm_obs_or_more:.3f}/{s_xg.p_value_rm_obs_or_more:.2f}). Same referee, same VAR team, same day. (2) Opponents are not favoured: they have {int(f_pm.nullified_for_opponents_in_rm_matches)} goals nullified vs RM vs {f_pm.expected:.1f} expected from their own per-match rate (p={f_pm.p_value_fewer_than_expected:.2f}) and {f_po.expected:.1f} offside-adjusted (ratio {f_po.ratio_obs_over_exp:.2f}). (3) Referees: Real Madrid's rate is homogeneous across the {int(rmeta.refs_with_8plus_rm_matches.iloc[0])} referees with 8+ Real Madrid matches (chi2 p={rmeta.p_value.iloc[0]:.2f}); {int(rmeta.refs_where_rm_rate_exceeds_same_ref_baseline.iloc[0])} of them have a higher RM rate than their rate for other teams - a pattern that is league-wide, not one referee. (4) Net points: Real Madrid lost {led_rm.points_lost:.0f} points to its own nullified goals and kept {led_rm.points_kept:.0f} thanks to opponents' - net {led_rm.net_points_from_nullified_goals:.0f}, similar to Villarreal (-9) and Barcelona (-7).", f_good),
        ("VAR accuracy (>95%) in context", f"VAR error cannot produce the excess. At 98.3% (Spitz et al. 2021, 2,195 matches, 13 countries) Real Madrid would have ~{acc.expected_wrong_rm_decisions.iloc[0]:.1f} wrong decisions out of {rm_n}; at 95%, ~{acc.expected_wrong_rm_decisions.iloc[2]:.1f}. The unexplained excess is ~{f_all.excess:.0f} goals. Even at a 20% error rate (more than double the 7.9% error of unaided referees in Spitz et al.) the chance that errors alone explain the excess is ~0 (see sheet 6). Nullified offsides are also geometric calls, the least subjective VAR category.", f_txt),
        ("Honest bottom line", "The outlier is real and only about half explained by volume. Nothing in the data indicates referee- or VAR-level targeting: the excess is spread across 15 referees, appears in the same-match comparison only as much as offside/goal-opportunity shares predict, opponents are not unusually spared, and VAR accuracy is too high for errors to matter at this scale. The residual ~2x is most consistent with Real Madrid's attacking profile (transition play with runners in behind, e.g. Mbappe/Vinicius/Benzema/Rodrygo) producing more goal-scored-then-offside events than shots/offside counts capture. That last point is a hypothesis: testing it needs tracking data (offside-line position at pass) which is not public. Also note small counts: 50 events, with 3 matches having 3 nullified goals each (clusters), and a CTA/RFEF audit of VAR correctness by beneficiary would be the decisive dataset.", f_warn),
        ("Pressing context (PPDA att / def)", f"Added as covariates: own PPDA att and def, and the opponent's PPDA att and def in the same match (log scale, Poisson GLM, same PPDA-complete sample of {int(pg_ref.n_team_matches):,} team-matches). The Real Madrid effect barely moves: {pg_ref.rm_irr:.2f}x without PPDA -> {pg_full.rm_irr:.2f}x with all four PPDA terms (95% CI {pg_full.irr_ci_low:.2f}-{pg_full.irr_ci_high:.2f}); top-10 only {pg_full10.rm_irr:.2f}x. Model trained on the other teams with PPDA predicts ~{pf_all.rm_expected:.0f} (95% {pf_all.expected_p2_5:.0f}-{pf_all.expected_p97_5:.0f}) vs {int(pf_all.rm_observed)} observed. Real Madrid presses like everyone else (PPDA {pp_rm.ppda:.1f} vs {pp_ot.ppda:.1f}) but opponents press Real Madrid much less (opponent PPDA {pp_rm.opp_ppda:.1f} vs {pp_ot.opp_ppda:.1f}; Real Madrid makes ~{pp_rm.opp_ppda_att:.0f} passes per match in that zone vs ~{pp_ot.opp_ppda_att:.0f}): that is a passing-volume/possession signature, not a pressing explanation of the nullified-goal excess. See sheet 6, section G2.", f_warn),
        ("Fouls, fouls in attack, yellow & red cards", f"Added over the same 2018-2026 window. Real Madrid commits far fewer fouls than other top-10 teams ({dp_rm.fouls:.1f} vs {dp_ot.fouls:.1f} per match), fewer in the attacking half ({dp_rm.fouls_att_half:.1f} vs {dp_ot.fouls_att_half:.1f}), fewer yellow cards ({dp_rm.yellow:.2f} vs {dp_ot.yellow:.2f}) and about the same red cards ({dp_rm.red:.2f} vs {dp_ot.red:.2f}); the attacking-half share of fouls is the same ({dp_rm.att_half_share:.0%} vs {dp_ot.att_half_share:.0%}). Nullified goals are negatively correlated with fouls across top-10 team-seasons (r=-0.40): possession-dominant teams foul less and score/lose more goals to offside. Adding total fouls, attacking-half fouls, yellow and red cards to the model leaves the Real Madrid effect at {dg_full.rm_irr:.2f}x (reference {dg_ref.rm_irr:.2f}x; 95% CI {dg_full.irr_ci_low:.2f}-{dg_full.irr_ci_high:.2f}); expected count ~{df_all.rm_expected:.0f} vs {int(df_all.rm_observed)} observed. By reason, the excess is mostly offside ({int(rs_off.rm_nullified)} of 50; {rs_off.rate_ratio:.1f}x others), with attacking-foul ({int(rs_fou.rm_nullified)}; {rs_fou.rate_ratio:.1f}x, small count) and handball ({int(rrt[(rrt.scope == 'All 20 teams per season') & (rrt.reason == 'Handball')].iloc[0].rm_nullified)}) too few to separate. See sheet 6, section G3.", f_warn),
        ("Clasico 26-Oct-2024 (Mbappe 65'/66') - goals ruled out on the pitch", f"A draft of your validated file contained a second Mbappe goal in the 0-4 Clasico at 65' (removed in the current 50-row version, which now matches this dataset one-to-one). It is real (commentary: 'The assistant referee raises his flag and the referee blows his whistle. Mbappe puts the ball into the net, but he is flagged for offside'; ESPN: Offside at 66') but it was NOT a VAR nullification: no VAR review in either feed, so the 50-goal VAR dataset correctly excludes it (the 30' Mbappe goal, which went to VAR, is rank 33). Mining the commentary of all 3,118 matches for goals ruled out on the pitch finds {on_tot} such events across all teams ({on_rm_n} Real Madrid), listed in sheet 12. Real Madrid is again first but the gap is smaller ({on_rm.rate_ratio:.1f}x raw, {on_glm_c.rm_irr:.1f}x after controls, p={on_glm_c.p_value:.2f}); VAR + on-field combined = {int(cb_rm.rm_events)} Real Madrid events ({cb_rm.rate_ratio:.1f}x). The extra Real Madrid effect at the VAR stage vs the on-field stage is {on_int.irr:.2f}x (95% CI {on_int.ci_low:.2f}-{on_int.ci_high:.2f}, p={on_int.p_value:.2f}): not significant - the excess is already there before VAR is involved. The 65' goal is kept only in sheet 12 (on-field dataset).", f_warn),
        *([("Players, matches affected, champion vs not, title scenarios (sheet 13)", f"Concentration: {e_k75} of {len(e_pc)} players account for 75% of the {int(e_pc.sum())} nullified goals (Benzema and Mbappe 8 each). Matches affected: the goals fall in {len(e_g)} matches ({100 * len(e_g) / int(e_ss.matches.sum()):.1f}% of Real Madrid league matches); {e_dl} ended in a draw or loss and in {e_chg} the result would have changed if every nullified goal had counted ({e_pts} points over 8.2 seasons). Champion vs not: {int(e_grp.loc['Champion', 'nullified'])} goals in {int(e_grp.loc['Champion', 'seasons'])} title seasons ({e_grp.loc['Champion', 'nullified'] / e_grp.loc['Champion', 'matches'] * 38:.1f} per 38) vs {int(e_grp.loc['Not champion', 'nullified'])} in {int(e_grp.loc['Not champion', 'seasons'])} non-title seasons ({e_grp.loc['Not champion', 'nullified'] / e_grp.loc['Not champion', 'matches'] * 38:.1f} per 38), not significantly different. Title scenarios (every season table rebuilt with the La Liga tie-break and re-ranked): counting ALL Real Madrid nullified goals as wrong changes only {', '.join(e_changed) or 'no title'}; with a realistic 2-5% VAR error rate the chance of overturning any title is at most {e_mc[e_mc.p_wrong <= 0.05].p_rm_champion.max():.1%}.", f_warn)] if HAVE_EDA else []),
        ("Sheets", "1_Tweet_Validation | 2_RM_Nullified_Goals | 3_All_Teams_Nullified | 4_Team_Ranking | 5_Attack_Volume_Top10 | 6_Stat_Framework | 7_RM_EDA | 8_Referees | 9_Net_Points_Ledger | 10_VAR_Accuracy_Refs | 11_Sources_Method_Limits | 12_OnField_Disallowed | 13_Titles_Players_Games", f_txt),
    ]
    rr_ = 3
    for k, v, fm in rows:
        if fm is None:
            ws.merge_range(rr_, 1, rr_, 2, k, f_h2); rr_ += 1; continue
        ws.write(rr_, 1, k, F(bold=True, text_wrap=True, valign="top"))
        ws.write(rr_, 2, v, fm)
        ws.set_row(rr_, max(30, 15 * (len(v) // 115 + 1)))
        rr_ += 1

    # ============================================================ 1 Tweet validation
    ws = wb.add_worksheet("1_Tweet_Validation"); xw.sheets["1_Tweet_Validation"] = ws
    ws.set_column(0, 0, 14); ws.set_column(1, 1, 24); ws.set_column(2, 12, 15)
    ws.write(0, 0, "I. Validation of MisterChip's post (10-Oct-2026): goals nullified by VAR, La Liga 2018-2026", f_title)
    ws.write(1, 0, "Reconstruction source: Flashscore 'Goal Disallowed' incidents (scorer, minute, reason) cross-checked with VAR commentary and ESPN match logs. 'before 10-Oct' removes the Vinicius goal the tweet counts as '+1 hoy'.", f_note)
    t = tw.copy()
    t.columns = ["Tweet rank", "Team", "Tweet count", "Reconstructed: all Flashscore incidents", "Reconstructed: VAR-confirmed (primary)",
                 "Reconstructed: before 10-Oct-2026", "Offside only", "Offside + attacking foul", "Diff vs tweet", "Diff %", "Reconstructed rank (all teams)"]
    ws.write(3, 0, "A. Tweet vs reconstruction", f_h3)
    end = put_df(ws, t, 4, 0, {"Diff %": fp})
    ws.set_row(4, 45)
    ws.write(end + 1, 0, "Reading: Real Madrid is #1 in both. The tweet's figures are systematically lower than a full reconstruction (except under the narrow 'offside+foul' definition for RM/Atletico/Celta), and the tweet's order of places 2-7 differs from ours (Barcelona is #3 here, #7 there). The +1 'hoy' is the Vinicius Junior goal ruled out for a foul at 71' vs Villarreal (confirmed).", f_note)
    ch = wb.add_chart({"type": "column"})
    ch.add_series({"name": "Tweet", "categories": ["1_Tweet_Validation", 5, 1, 11, 1], "values": ["1_Tweet_Validation", 5, 2, 11, 2], "fill": {"color": "#A6A6A6"}})
    ch.add_series({"name": "Reconstructed (before 10-Oct)", "categories": ["1_Tweet_Validation", 5, 1, 11, 1], "values": ["1_Tweet_Validation", 5, 5, 11, 5], "fill": {"color": "#1F3864"}})
    ch.set_title({"name": "Tweet vs reconstruction (VAR-nullified goals)"}); ch.set_size({"width": 720, "height": 320})
    ws.insert_chart(end + 4, 0, ch)
    r0 = end + 22
    ws.write(r0, 0, "B. Independent check: ESPN's own 'GOAL OVERTURNED BY VAR' log vs Flashscore (seasons 2023-24 to 2026-27)", f_h3)
    e2 = espn.head(14).rename(columns={"team": "Team", "espn_overturned_goals": "ESPN overturned goals", "flashscore_nullified_goals": "Flashscore nullified goals",
                                       "espn_rank": "ESPN rank", "flashscore_rank": "Flashscore rank", "share_espn_pct": "ESPN share %", "share_flashscore_pct": "Flashscore share %"})
    end = put_df(ws, e2, r0 + 1, 0, {"ESPN share %": fp, "Flashscore share %": fp})
    ws.write(end, 0, "ESPN labels fewer events (it only started tagging overturned goals explicitly in 2022-23), but both sources rank Real Madrid first with the same share (~12.5%) - the outlier does not depend on one provider's logging habits.", f_note)
    r0 = end + 3
    ws.write(r0, 0, "C. Your 4-row sample vs source data", f_h3)
    samp = pd.DataFrame([
        ["1", "2018-09-26", "Sevilla", "Luka Modric", "53 / 2nd", "Alejandro Hernandez Hernandez", "OK", "Flashscore: Goal Disallowed (offside) 54'; ESPN: Modric flagged offside 53', VAR review 54'. Referee confirmed (Transfermarkt). Minute 53 (offside flag) vs 54 (decision)."],
        ["2", "2018-10-20", "Levante", "Marco Asensio", "43 / first", "Guillermo Cuadra Fernandez", "FIX minute", "Flashscore: Asensio goal disallowed (offside) at 18'; ESPN: 'Video Review' at 18'. The 43' event in ESPN is a Levante offside (Marti/Tono), not Real Madrid. Half = first is right; minute should be 18. Score 1-2 and referee are right."],
        ["3", "2018-12-01", "Valencia", "Karim Benzema", "55 / 2nd", "Jose Luis Gonzalez Gonzalez", "NOT SUPPORTED", "No 'Goal Disallowed' incident in Flashscore; ESPN has no VAR review in this match (only RM offsides at 42' (Benzema) and 59' (Vazquez); at 54'-55' Benzema/Modric shots missed). Referee and 2-0 score are right, but there is no evidence of a VAR nullified goal. If it was an assistant-referee flag on the pitch it is not a VAR nullification."],
        ["4", "2019-03-10", "Real Valladolid", "Luka Modric / Raphael Varane", "55 / 2nd", "Jesus Gil Manzano", "FIX (mixed matches)", "Modric (scorer) / Varane (offside in build-up) is the Celta match: 2019-03-16, 56', Real Madrid 2-0 Celta, home, referee Juan Martinez Munuera. The 10-Mar-2019 Valladolid 1-4 RM match (referee Gil Manzano) only had a Valladolid goal (Guardiola, 14') ruled out - in Real Madrid's favour."],
    ], columns=["Your row", "Date", "Rival", "Players", "Minute / half", "Referee", "Verdict", "Evidence"])
    end = put_df(ws, samp.iloc[:, :7], r0 + 1, 0, {c: f_txt for c in samp.columns[:7]})
    ws.merge_range(r0 + 1, 7, r0 + 1, 14, "Evidence", f_hdr)
    for i, ev in enumerate(samp.Evidence):
        ws.merge_range(r0 + 2 + i, 7, r0 + 2 + i, 14, ev, f_txt)
        ws.set_row(r0 + 2 + i, 64)
    ws.write(end, 0, "Your column semantics preserved: active_player = goal scorer (the player whose goal is nullified); passive_player = other player flagged offside in the build-up (from ESPN offside events; blank when the scorer himself was offside or ESPN does not name the player).", f_note)
    r0 = end + 3
    ws.write(r0, 0, "D. Data-quality cross-check of attack stats (Flashscore vs ESPN vs Understat)", f_h3)
    s2 = sv.rename(columns={"metric": "Metric", "team_matches_compared": "Team-matches compared", "pearson_r": "Pearson r", "exact_match_pct": "Exact match %",
                            "within_1_pct": "Within +/-1 % (xG: within 0.25)", "mean_flashscore": "Mean (Flashscore)", "mean_espn": "Mean (ESPN / Understat for xG)", "mean_abs_diff": "Mean abs diff"})
    end = put_df(ws, s2, r0 + 1, 0, {"Pearson r": f3, "Exact match %": f1, "Within +/-1 % (xG: within 0.25)": f1, "Mean (Flashscore)": f2, "Mean (ESPN / Understat for xG)": f2, "Mean abs diff": f3})
    ws.set_row(r0 + 1, 45)
    ws.write(end, 0, "Shots, shots on target, offsides and corners agree across two independent providers in >95% of team-matches; Understat xG (used for all seasons) tracks Flashscore xG at r=0.93.", f_note)

    # ============================================================ 2 RM breakdown
    def write_breakdown(name, df, title, note):
        ws = wb.add_worksheet(name); xw.sheets[name] = ws
        ws.write(0, 0, title, f_title)
        ws.write(1, 0, note, f_note)
        fm = {"points_at_time": f0, "league_position_at_time": f0, "rival_position_at_time": f0, "round": f0, "minute": f0}
        cols = list(df.columns)
        end = put_df(ws, df, 3, 0, fm)
        if "links" in df.columns:                                   # clickable video links
            lc = list(df.columns).index("links")
            for i_, u_ in enumerate(df["links"]):
                if isinstance(u_, str) and u_.startswith("http"):
                    ws.write_url(4 + i_, lc, u_, F(font_color="#0563C1", underline=1), string=u_)
        widths = {"rank": 6, "date": 11, "season": 10, "round": 8, "team (goal nullified)": 20, "rival": 20, "active_player": 20, "passive_player": 18,
                  "local_flag": 9, "var_reason": 14, "context_category": 30, "minute": 7, "minute_display": 9, "half": 8, "score_before_goal (team-opp)": 12,
                  "what_the_goal_would_have_been": 18, "team_goals_final": 9, "rival_goals_final": 9, "outcome": 9, "points_lost_due_to_nullification": 12,
                  "league_position_at_time": 12, "rival_position_at_time": 12, "points_at_time": 10, "referee_on_field": 28, "laliga_title_won_flag": 11,
                  "la_liga_champion": 24, "var_decision_text": 90, "var_evidence": 26, "manual_validation": 12, "links": 48}
        for j, c in enumerate(cols):
            ws.set_column(j, j, widths.get(c, 12))
        ws.set_row(3, 52)
        ws.freeze_panes(4, 3)
        ws.autofilter(3, 0, end - 1, len(cols) - 1)
        return ws

    note = ("One row per goal ruled out after VAR review. Columns up to 'outcome'/'referee' follow your sample layout; additions: context_category, score_before_goal, "
            "what_the_goal_would_have_been, points_lost_due_to_nullification, league position/points at kick-off (table rebuilt from results; round-1 = blank), VAR decision text. "
            "referee_on_field = main referee (VAR-room official not available). Sources: Flashscore incidents/commentary, ESPN logs, Transfermarkt (referee names). local_flag TRUE = home. "
            "manual_validation / links: manual check flag and video link taken from your file RM_nullified_goals_breakdown_validated.xlsx (matched on date, player and minute; 50 of 50 flagged TRUE).")
    write_breakdown("2_RM_Nullified_Goals", RM_B, f"II. Real Madrid goals nullified by VAR, 2018-19 to 12-Oct-2026 (n = {len(RM_B)})", note)
    write_breakdown("3_All_Teams_Nullified", ALL_B, f"All La Liga teams: VAR-nullified goals 2018-19 to 12-Oct-2026 (n = {len(ALL_B)})",
                    "Same schema as sheet 2 for every team, so the Real Madrid rows can be compared with the rest of the league. 'team (goal nullified)' is the team whose goal was ruled out.")

    # ============================================================ 4 Team ranking
    ws = wb.add_worksheet("4_Team_Ranking"); xw.sheets["4_Team_Ranking"] = ws
    ws.write(0, 0, "Nullified goals by team (VAR-confirmed), 2018-19 to 12-Oct-2026", f_title)
    ws.set_column(0, 0, 7); ws.set_column(1, 1, 22); ws.set_column(2, 12, 13)
    end = put_df(ws, team_tbl, 2, 0, {"Nullified / match": f3, "Nullified per 100 goal events": f2})
    ws.set_row(2, 45)
    ch = wb.add_chart({"type": "bar"})
    ch.add_series({"name": "Nullified goals", "categories": ["4_Team_Ranking", 3, 1, 14, 1], "values": ["4_Team_Ranking", 3, 2, 14, 2], "fill": {"color": "#1F3864"},
                   "points": [{"fill": {"color": "#C00000"}}] + [{}] * 11})
    ch.set_title({"name": "Top 12 teams: VAR-nullified goals 2018-2026"}); ch.set_y_axis({"reverse": True}); ch.set_legend({"none": True}); ch.set_size({"width": 560, "height": 380})
    ws.insert_chart(2, 13, ch)
    r0 = end + 2
    ws.write(r0, 0, "By season", f_h3)
    end = put_df(ws, season_mat, r0 + 1, 1)
    ws.write(end + 1, 1, "2026-27 is partial (8 rounds).", f_note)
    r0 = end + 3
    ws.write(r0, 0, "Real Madrid per season vs the average other top-10 team (normalised to 38 matches)", f_h3)
    end = put_df(ws, season_cmp, r0 + 1, 1, {"RM nullified per 38 matches": f1, "Avg other top-10 team (per 38 matches)": f1, "RM xG": f1})
    ch = wb.add_chart({"type": "column"})
    ch.add_series({"name": "Real Madrid (per 38)", "categories": ["4_Team_Ranking", r0 + 2, 1, r0 + 10, 1], "values": ["4_Team_Ranking", r0 + 2, 3, r0 + 10, 3], "fill": {"color": "#C00000"}})
    ch.add_series({"name": "Avg other top-10 team (per 38)", "categories": ["4_Team_Ranking", r0 + 2, 1, r0 + 10, 1], "values": ["4_Team_Ranking", r0 + 2, 4, r0 + 10, 4], "fill": {"color": "#1F3864"}})
    ch.set_title({"name": "Nullified goals per 38 matches: Real Madrid vs other top-10 teams"}); ch.set_size({"width": 700, "height": 320})
    ws.insert_chart(end + 1, 1, ch)

    # ============================================================ 5 Attack volume
    ws = wb.add_worksheet("5_Attack_Volume_Top10"); xw.sheets["5_Attack_Volume_Top10"] = ws
    ws.write(0, 0, "Addendum item 3 - attacking volume vs VAR-nullified goals (top-10 of each season's final table; relegated teams excluded by construction)", f_title)
    ws.write(1, 0, "Scope: for each season the 10 best teams in the final table (2026-27: current table, 8 rounds - partial). Chances created = shots, shots on target, xG (Understat; Flashscore xG for 2026-27 if missing). Offsides = offside calls against the team's attackers (offsides in attacking positions). Sources cross-checked in sheet 1-D.", f_note)
    ws.set_column(0, 0, 22); ws.set_column(1, 24, 12)
    a = agg.copy()
    for c in ("shots", "sot", "xg", "offsides"):
        a[f"{c}_rank"] = a[f"{c}_pm"].rank(ascending=False, method="min").astype(int)
    a["dis_rank"] = a.dis_pm.rank(ascending=False, method="min").astype(int)
    a["dis_per_100_shots"] = 100 * a.dis / a.shots
    a["dis_per_100_offsides"] = 100 * a.dis / a.offsides
    a = a.sort_values("shots_pm", ascending=False)
    ranking = a[["team", "seasons", "matches", "dis", "dis_pm", "dis_rank", "shots", "shots_pm", "shots_rank", "sot", "sot_pm", "sot_rank", "xg", "xg_pm", "xg_rank",
                 "offsides", "offsides_pm", "offsides_rank", "dis_per_100_shots", "dis_per_100_offsides",
                 "ppda_att_pm", "ppda_def_pm", "ppda_pm", "opp_ppda_att_pm", "opp_ppda_def_pm", "opp_ppda_pm",
                 "fouls_pm", "fouls_att_pm", "fouls_def_pm", "yellow_pm", "red_pm", "fouls_att_share_pm"]]
    ranking.columns = ["Team", "Seasons in top 10", "Matches", "Nullified goals", "Nullified / match", "Rank: nullified", "Shots", "Shots / match", "Rank: shots", "Shots on target",
                       "SOT / match", "Rank: SOT", "xG", "xG / match", "Rank: xG", "Offsides", "Offsides / match", "Rank: offsides", "Nullified per 100 shots", "Nullified per 100 offsides",
                       "PPDA att / match (opp. passes in pressing zone)", "PPDA def / match (own defensive actions)", "PPDA (att/def; lower = more pressing)",
                       "Opp. PPDA att / match (own passes vs opp. press)", "Opp. PPDA def / match (opp. defensive actions)", "Opp. PPDA (att/def)",
                       "Fouls committed / match", "Fouls committed in attacking half / match", "Fouls committed in defensive half / match",
                       "Yellow cards / match", "Red cards / match", "Share of located fouls in attacking half (att/total)"]
    ws.write(3, 0, "A. Team ranking over 2018-2026 (top-10 seasons only), sorted by shots per match", f_h3)
    fm = {c: f2 for c in ranking.columns if "/" in c or "per 100" in c or c == "xG"}
    end = put_df(ws, ranking, 4, 0, fm)
    ws.set_row(4, 45)
    ch = wb.add_chart({"type": "scatter"})
    n_ = len(ranking)
    rm_i = ranking.index.get_loc(ranking[ranking.Team == RM].index[0]) if False else int(np.where(ranking.Team.values == RM)[0][0])
    ch.add_series({"name": "Other teams", "categories": ["5_Attack_Volume_Top10", 5, 7, 4 + n_, 7], "values": ["5_Attack_Volume_Top10", 5, 4, 4 + n_, 4],
                   "marker": {"type": "circle", "size": 7, "fill": {"color": "#1F3864"}}})
    ch.add_series({"name": "Real Madrid", "categories": ["5_Attack_Volume_Top10", 5 + rm_i, 7, 5 + rm_i, 7], "values": ["5_Attack_Volume_Top10", 5 + rm_i, 4, 5 + rm_i, 4],
                   "marker": {"type": "diamond", "size": 11, "fill": {"color": "#C00000"}}})
    ch.set_title({"name": "Nullified goals per match vs shots per match (top-10 teams, aggregate)"}); ch.set_x_axis({"name": "Shots per match", "min": 8}); ch.set_y_axis({"name": "Nullified goals / match", "min": 0})
    ch.set_size({"width": 560, "height": 360})
    ws.insert_chart(end + 2, 0, ch)
    ch2 = wb.add_chart({"type": "scatter"})
    ch2.add_series({"name": "Other teams", "categories": ["5_Attack_Volume_Top10", 5, 16, 4 + n_, 16], "values": ["5_Attack_Volume_Top10", 5, 4, 4 + n_, 4], "marker": {"type": "circle", "size": 7, "fill": {"color": "#1F3864"}}})
    ch2.add_series({"name": "Real Madrid", "categories": ["5_Attack_Volume_Top10", 5 + rm_i, 16, 5 + rm_i, 16], "values": ["5_Attack_Volume_Top10", 5 + rm_i, 4, 5 + rm_i, 4], "marker": {"type": "diamond", "size": 11, "fill": {"color": "#C00000"}}})
    ch2.set_title({"name": "Nullified goals per match vs offsides per match (top-10 teams, aggregate)"}); ch2.set_x_axis({"name": "Offsides per match (attacking positions)", "min": 1.5}); ch2.set_y_axis({"name": "Nullified goals / match", "min": 0})
    ch2.set_size({"width": 560, "height": 360})
    ws.insert_chart(end + 2, 8, ch2)
    r0 = end + 22
    ws.write(r0, 0, "B. Correlations: VAR-nullified goals vs attack volume and vs offsides", f_h3)
    cc = corr.rename(columns={"scope": "Scope", "x": "X", "y": "Y", "n": "n", "pearson_r": "Pearson r", "pearson_p": "p (Pearson)", "pearson_ci_low": "95% CI low", "pearson_ci_high": "95% CI high",
                              "spearman_rho": "Spearman rho", "spearman_p": "p (Spearman)", "kendall_tau": "Kendall tau", "kendall_p": "p (Kendall)"})
    end = put_df(ws, cc, r0 + 1, 0, {c: f3 for c in cc.columns if c not in ("Scope", "X", "Y", "n")})
    ws.set_row(r0 + 1, 30)
    ws.write(end, 0, "Bootstrap 95% CI (2,000 resamples). Team-season rows are not fully independent (same club across seasons); the team-level (n = number of teams) block is the conservative view. Excluding Real Madrid lowers the shots/xG correlations (r~0.3-0.4) and leaves offsides weak (r~0.2): the correlations are not created by Real Madrid alone.", f_note)
    r0 = end + 3
    ws.write(r0, 0, "C. Team-season data (top-10 scope; Real Madrid rows first)", f_h3)
    tsd = ts[ts.top10].copy()
    tsd["is_rm"] = (tsd.team == RM)
    tsd = tsd.sort_values(["is_rm", "season", "final_pos"], ascending=[False, True, True])
    tsd = tsd[["season", "team", "final_pos", "matches", "goals", "shots", "sot", "xg", "offsides", "corners", "dis", "shots_pm", "sot_pm", "xg_pm", "offsides_pm", "dis_pm",
               "dis_per_100_shots", "dis_per_100_offsides", "dis_per_100_goal_events", "partial_season",
               "ppda_att_pm", "ppda_def_pm", "ppda_pm", "opp_ppda_att_pm", "opp_ppda_def_pm", "opp_ppda_pm",
               "fouls_pm", "fouls_att_pm", "fouls_def_pm", "yellow_pm", "red_pm", "fouls_att_share_pm"]]
    tsd.columns = ["Season", "Team", "Final pos", "Matches", "Goals", "Shots", "SOT", "xG", "Offsides", "Corners", "Nullified", "Shots/match", "SOT/match", "xG/match", "Offsides/match",
                   "Nullified/match", "Nullified per 100 shots", "Nullified per 100 offsides", "Nullified per 100 goal events", "Partial season",
                   "PPDA att/match", "PPDA def/match", "PPDA (att/def)", "Opp. PPDA att/match", "Opp. PPDA def/match", "Opp. PPDA (att/def)",
                   "Fouls/match", "Fouls in attacking half/match", "Fouls in defensive half/match", "Yellow cards/match", "Red cards/match", "Attacking-half share of fouls (att/total)"]
    end = put_df(ws, tsd, r0 + 1, 0, {c: f2 for c in tsd.columns if "/" in c or "per 100" in c or c == "xG"})
    ws.set_row(r0 + 1, 30)

    # ============================================================ 6 Stat framework
    ws = wb.add_worksheet("6_Stat_Framework"); xw.sheets["6_Stat_Framework"] = ws
    ws.set_column(0, 0, 34); ws.set_column(1, 14, 14)
    ws.write(0, 0, "III. Statistical and experimental framework", f_title)
    ws.merge_range(2, 0, 2, 12, "Design", f_h2)
    design = [
        ("Question", "Is Real Madrid's count of VAR-nullified goals (50) too large to be explained by how much and how it attacks, and does the pattern look like targeting (against Real Madrid) or favouritism (towards opponents)?"),
        ("H0 (neutral officiating)", "A team's nullified goals are Poisson with a rate that depends only on its attacking exposure (matches, shots, xG, offsides, goal opportunities). Real Madrid has no special effect."),
        ("H1a (targeting)", "Real Madrid has a rate above that implied by exposure, AND the excess appears within matches (same referee/VAR team) as opponents being spared, AND/OR concentrates in specific referees."),
        ("H1b (profile)", "Real Madrid has a rate above that implied by simple exposure, but the excess is symmetric within matches and spread over referees - i.e. attacking profile (more goal-scored-then-offside/foul events), not bias."),
        ("Outcome", "Goals nullified after VAR review (394 events; 3 more Flashscore incidents lack explicit VAR evidence and are excluded from tests)."),
        ("Unit / exposure", "Team-match (6,236 rows). Exposures: matches, shots, shots on target, xG, offsides, corners, goals+nullified ('goal events')."),
        ("Controls", "Season, home/away, offsides (log), shots (log), xG. Standard errors clustered by match (both teams share a referee)."),
        ("Why not only counts?", "Real Madrid plays top-10-type opponents and attacks more; a raw count compares unlike things. Tests A-F below move from raw to exposure-adjusted to within-match comparisons."),
    ]
    rr_ = 3
    for k, v in design:
        ws.write(rr_, 0, k, F(bold=True, valign="top")); ws.merge_range(rr_, 1, rr_, 12, v, f_txt); ws.set_row(rr_, 30); rr_ += 1
    rr_ += 1
    ws.merge_range(rr_, 0, rr_, 12, "A. Rate ratios: Real Madrid vs all other teams (exact conditional Poisson test)", f_h2); rr_ += 1
    rt = rate.rename(columns={"scope": "Scope", "exposure": "Exposure", "rm_nullified": "RM nullified", "rm_exposure": "RM exposure", "rm_rate": "RM rate", "others_nullified": "Others nullified",
                              "others_exposure": "Others exposure", "others_rate": "Others rate", "rate_ratio": "Rate ratio", "rr_ci_low": "95% CI low", "rr_ci_high": "95% CI high", "p_one_sided": "p (one-sided)"})
    rr_ = put_df(ws, rt, rr_, 0, {"RM exposure": f1, "RM rate": f3, "Others exposure": f1, "Others rate": f3, "Rate ratio": f2, "95% CI low": f2, "95% CI high": f2, "p (one-sided)": fpv}) + 1
    ws.merge_range(rr_, 0, rr_, 12, f"Reading: whichever exposure is used, Real Madrid's rate is {rate.rate_ratio.min():.1f}x-{rate.rate_ratio.max():.1f}x that of other teams (all p<{max(rate.p_one_sided.max(), 0.001):.3f}). Normalising by attacking volume shrinks but never removes the gap.", f_note); rr_ += 2
    ws.merge_range(rr_, 0, rr_, 12, "B. Poisson regression, RM indicator with progressively more controls (IRR = incident rate ratio; SE clustered by match)", f_h2); rr_ += 1
    gl = glm.rename(columns={"scope": "Scope", "model": "Model", "n_team_matches": "n team-matches", "rm_irr": "RM IRR", "irr_ci_low": "95% CI low", "irr_ci_high": "95% CI high", "p_value": "p",
                             "pearson_dispersion": "Dispersion", "aic": "AIC", "off_coef": "log(offsides) coef", "off_p": "p offsides", "shots_coef": "log(shots) coef", "shots_p": "p shots"})
    rr_ = put_df(ws, gl, rr_, 0, {c: f3 for c in gl.columns if c not in ("Scope", "Model", "n team-matches")}) + 1
    ws.merge_range(rr_, 0, rr_, 12, f"Reading: the RM effect goes {m_raw.rm_irr:.2f}x -> {m_full.rm_irr:.2f}x (all teams, full controls), {m_t10.rm_irr:.2f}x (top-10 only). Offsides and shots are both strongly significant drivers (so they are the right variables) but they do not absorb the Real Madrid effect. Dispersion ~1.03-1.1: Poisson is adequate.", f_note); rr_ += 2
    ws.merge_range(rr_, 0, rr_, 12, "C. Leave-Real-Madrid-out forecast (Monte Carlo, 20,000 draws): how many would Real Madrid have if it behaved like the other teams given its attack?", f_h2); rr_ += 1
    fcc = fc.rename(columns={"scope": "Scope", "model_trained_on_other_teams": "Model trained on other teams", "rm_matches": "RM matches", "rm_observed": "RM observed", "rm_expected": "RM expected",
                             "expected_p2_5": "Expected 2.5%", "expected_p97_5": "Expected 97.5%", "excess": "Excess", "obs_over_expected": "Obs / expected", "p_value_obs_or_more": "p (obs or more)", "dispersion_used": "Dispersion"})
    rr_ = put_df(ws, fcc, rr_, 0, {"RM expected": f1, "Excess": f1, "Obs / expected": f2, "p (obs or more)": fpv, "Dispersion": f2}) + 1
    ws.merge_range(rr_, 0, rr_, 12, f"Reading: with the richest model Real Madrid is expected to have ~{f_all.rm_expected:.0f} (95% {f_all.expected_p2_5:.0f}-{f_all.expected_p97_5:.0f}); observed {int(f_all.rm_observed)}. Attack volume explains about half; the rest (~{f_all.excess:.0f}) is a ~2x residual.", f_note); rr_ += 2
    ws.merge_range(rr_, 0, rr_, 12, "D. Same-match natural experiment: in Real Madrid matches (same referee, VAR room, pitch, day), is the RM/opponent split of nullified goals what attack shares predict?", f_h2); rr_ += 1
    sy = sym.rename(columns={"null_model": "Null model", "rm_matches": "RM matches", "nullified_rm": "Nullified: RM", "nullified_opponents": "Nullified: opponents", "expected_rm": "Expected RM", "expected_p2_5": "Exp. 2.5%",
                             "expected_p97_5": "Exp. 97.5%", "p_value_rm_obs_or_more": "p (RM obs or more)", "rm_share_of_nullified": "RM observed share", "mean_rm_attack_share": "RM mean attack share"})
    rr_ = put_df(ws, sy, rr_, 0, {"Expected RM": f1, "p (RM obs or more)": fpv, "RM observed share": f3, "RM mean attack share": f3}) + 1
    ws.merge_range(rr_, 0, rr_, 12, f"Reading: conditional on how many goals were nullified in each match, RM's share ({s_off.rm_share_of_nullified:.0%}) is statistically in line with its share of offsides (p={s_off.p_value_rm_obs_or_more:.2f}) and goal opportunities (p={s_go.p_value_rm_obs_or_more:.2f}). It is above what shots/xG shares alone predict (p={s_shots.p_value_rm_obs_or_more:.3f}/{s_xg.p_value_rm_obs_or_more:.2f}), consistent with offside-prone attacking rather than one-sided treatment: if VAR/referees leaned against RM within matches, the offside-share and goal-opportunity nulls would be rejected.", f_note); rr_ += 2
    ws.merge_range(rr_, 0, rr_, 12, "E. Favouritism test: are Real Madrid's opponents spared in those matches?", f_h2); rr_ += 1
    fv = fav.rename(columns={"baseline": "Baseline for opponents' expected nullified goals", "matches_vs_rm": "Matches vs RM", "nullified_for_opponents_in_rm_matches": "Observed (opponents, vs RM)", "expected": "Expected",
                             "ratio_obs_over_exp": "Obs / expected", "p_value_fewer_than_expected": "p (fewer than expected)"})
    rr_ = put_df(ws, fv, rr_, 0, {"Expected": f1, "Obs / expected": f2, "p (fewer than expected)": f3}) + 1
    ws.merge_range(rr_, 0, rr_, 12, f"Reading: opponents have fewer nullified goals against RM than their season-average per match ({f_pm.ratio_obs_over_exp:.2f}x) but not significantly (p={f_pm.p_value_fewer_than_expected:.2f}) and not at all once their offside count is considered ({f_po.ratio_obs_over_exp:.2f}x). No statistical sign of opponents being systematically protected.", f_note); rr_ += 2
    ws.merge_range(rr_, 0, rr_, 12, "F. Robustness: clustering (is it a few multi-goal matches?) and referee homogeneity", f_h2); rr_ += 1
    clc = cl.rename(columns={"scope": "Scope", "rm_matches_with_nullified": "RM matches with >=1", "rm_matches": "RM matches", "rm_pct": "RM %", "others_matches_with_nullified": "Others matches with >=1",
                             "others_team_matches": "Others team-matches", "others_pct": "Others %", "odds_ratio": "Odds ratio", "p_one_sided": "p (Fisher)", "rm_max_nullified_in_one_match": "RM max in one match",
                             "rm_nullified_in_multi_goal_matches": "RM goals in multi-goal matches"})
    rr_ = put_df(ws, clc, rr_, 0, {"RM %": f1, "Others %": f1, "Odds ratio": f2, "p (Fisher)": fpv}) + 1
    rme = rmeta.rename(columns={"refs_with_8plus_rm_matches": "Referees with 8+ RM matches", "chi2_heterogeneity": "Chi2 heterogeneity", "dof": "dof", "p_value": "p",
                                "refs_where_rm_rate_exceeds_same_ref_baseline": "Referees where RM rate > their rate for other teams"})
    rr_ = put_df(ws, rme, rr_ + 1, 0, {"Chi2 heterogeneity": f2, "p": f3}) + 1
    c0 = cl.iloc[0]
    ws.merge_range(rr_, 0, rr_, 12, f"Reading: the excess is not an artefact of a few multi-goal matches: even counting 'matches with at least one nullified goal', RM is {c0.rm_pct:.1f}% vs {c0.others_pct:.1f}% (odds {c0.odds_ratio:.1f}x). RM's rate does not differ significantly between referees (p={rmeta.p_value.iloc[0]:.2f}) and is above the same referee's baseline for {int(rmeta.refs_where_rm_rate_exceeds_same_ref_baseline.iloc[0])} of {int(rmeta.refs_with_8plus_rm_matches.iloc[0])} referees - a league-wide pattern, no 'one referee' story. Detail in sheet 8.", f_note); rr_ += 2
    ws.merge_range(rr_, 0, rr_, 12, "G. VAR accuracy stress test: could VAR error explain the excess?", f_h2); rr_ += 1
    ac = acc.rename(columns={"accuracy_scenario": "Accuracy scenario", "assumed_error_rate": "Error rate", "rm_decisions": "RM nullifications", "expected_wrong_rm_decisions": "Expected wrong RM decisions",
                             "p_at_least_10_wrong": "P(>=10 wrong)", "excess_to_explain": "Excess to explain (obs - expected)", "p_wrong_decisions_ge_excess": "P(wrong >= excess)"})
    rr_ = put_df(ws, ac, rr_, 0, {"Error rate": f3, "Expected wrong RM decisions": f2, "P(>=10 wrong)": fpv, "P(wrong >= excess)": fpv}) + 1
    ws.merge_range(rr_, 0, rr_, 12, f"Reading: even if every VAR error went against Real Madrid, a 95-98% accurate VAR yields ~1-2.5 wrong decisions among {rm_n}, versus an unexplained excess of ~{f_all.excess:.0f}. VAR error is not a viable explanation; a bias story would have to operate through *which incidents get flagged/reviewed*, which tests D-F do not support.", f_note); rr_ += 2
    ws.merge_range(rr_, 0, rr_, 12, "G2. Pressing context: PPDA att and PPDA def as covariates (own pressing and the pressing Real Madrid faces)", f_h2); rr_ += 1
    ws.merge_range(rr_, 0, rr_, 12, "Definitions (Understat): PPDA att = opponent passes in the pressing zone; PPDA def = the team's own defensive actions (tackles, interceptions, challenges, fouls) in that zone; PPDA = att / def, lower = more intense pressing. 'Opp.' versions are the same quantities for the opponent in the same match (the opponent's PPDA att = the team's own passes in the zone where the opponent presses). Models are log-linear in each component, all on the same PPDA-complete sample so Real Madrid's IRR is comparable across rows.", f_note); ws.set_row(rr_, 45); rr_ += 1
    ws.write(rr_, 0, "(i) Pressing profile per match", f_h3); rr_ += 1
    prf = ppr.rename(columns={"scope": "Scope", "group": "Group", "team_matches": "Team-matches", "ppda_att": "PPDA att", "ppda_def": "PPDA def", "ppda": "PPDA",
                              "opp_ppda_att": "Opp. PPDA att", "opp_ppda_def": "Opp. PPDA def", "opp_ppda": "Opp. PPDA", "nullified_per_match": "Nullified / match"})
    rr_ = put_df(ws, prf, rr_, 0, {c: f2 for c in prf.columns if c not in ("Scope", "Group", "Team-matches")}) + 1
    ws.write(rr_, 0, "(ii) Real Madrid IRR with and without PPDA terms", f_h3); rr_ += 1
    pgx = pg.rename(columns={"scope": "Scope", "model": "Model", "n_team_matches": "n team-matches", "rm_irr": "RM IRR", "irr_ci_low": "95% CI low", "irr_ci_high": "95% CI high",
                             "p_value": "p", "aic": "AIC", "pearson_dispersion": "Dispersion"})
    rr_ = put_df(ws, pgx, rr_, 0, {c: f3 for c in pgx.columns if c not in ("Scope", "Model", "n team-matches")}) + 1
    ws.write(rr_, 0, "(iii) Coefficients of the full PPDA model (IRR per 1-unit change in the log variable; CI clustered by match)", f_h3); rr_ += 1
    pcx = pcf.rename(columns={"scope": "Scope", "variable": "Variable", "coef": "Coef", "irr": "IRR", "ci_low": "95% CI low", "ci_high": "95% CI high", "p_value": "p"})
    rr_ = put_df(ws, pcx, rr_, 0, {c: f3 for c in pcx.columns if c not in ("Scope", "Variable")}) + 1
    ws.write(rr_, 0, "(iv) Leave-Real-Madrid-out forecast with PPDA", f_h3); rr_ += 1
    pfx = pfc.rename(columns={"scope": "Scope", "model_trained_on_other_teams": "Model trained on other teams", "rm_matches": "RM matches", "rm_observed": "RM observed", "rm_expected": "RM expected",
                              "expected_p2_5": "Expected 2.5%", "expected_p97_5": "Expected 97.5%", "excess": "Excess", "obs_over_expected": "Obs / expected", "p_value_obs_or_more": "p (obs or more)", "dispersion_used": "Dispersion"})
    rr_ = put_df(ws, pfx, rr_, 0, {"RM expected": f1, "Excess": f1, "Obs / expected": f2, "p (obs or more)": fpv, "Dispersion": f2}) + 1
    ws.merge_range(rr_, 0, rr_, 12, f"Reading: PPDA does not absorb the Real Madrid effect: IRR {pg_ref.rm_irr:.2f} -> {pg_full.rm_irr:.2f} (all teams) and the expected count stays ~{pf_all.rm_expected:.0f} vs {int(pf_all.rm_observed)} observed. Offsides remain the dominant driver (IRR ~2.35 per log-unit). Real Madrid's own pressing is average, while opponents press it far less (opponent PPDA {pp_rm.opp_ppda:.1f} vs {pp_ot.opp_ppda:.1f}): consistent with Real Madrid having the ball and passing more in that zone, i.e. an attack-volume signature already covered by the shots/xG controls. PPDA att and def are correlated with each other by construction, so individual PPDA coefficients are imprecise (most CIs include 1); the useful result is the stability of the Real Madrid coefficient. Correlations with PPDA components are in sheet 5-B.", f_note); ws.set_row(rr_, 75); rr_ += 2
    ws.merge_range(rr_, 0, rr_, 12, "G3. Discipline context: fouls committed, fouls committed in attack, yellow cards and red cards (same 2018-19 to 12-Oct-2026 window)", f_h2); rr_ += 1
    ws.merge_range(rr_, 0, rr_, 12, "Definitions: total fouls, yellow and red cards = Flashscore match statistics (fouls cross-checked with ESPN, r=0.94; red cards count straight reds incl. second yellows as published). Fouls in the attacking half = fouls the team committed in ITS OWN attacking half, taken from ESPN commentary: a free kick the opponent 'wins in the defensive half' is a foul committed in the committer's attacking half (verified: forwards produce this tag 78% of the time, defenders ~44%). Also shown: defensive half, wing (half not stated by ESPN) and own penalty area. ESPN logs ~91% of box-score fouls, so zone counts are slightly below totals and are best read as shares. These are fouls by the team in general, not only fouls leading to a nullified goal; the nullified goals caused by an attacking foul are analysed by reason in (v).", f_note); ws.set_row(rr_, 75); rr_ += 1
    ws.write(rr_, 0, "(i) Discipline profile per match", f_h3); rr_ += 1
    dpx = dpr.rename(columns={"scope": "Scope", "group": "Group", "team_matches": "Team-matches", "fouls": "Fouls", "fouls_att_half": "Fouls in attacking half", "fouls_def_half": "Fouls in defensive half",
                              "fouls_wing": "Fouls on wings", "fouls_own_box": "Fouls in own box", "att_half_share": "Attacking-half share", "yellow": "Yellow cards", "red": "Red cards",
                              "nullified_per_match": "Nullified goals / match"})
    rr_ = put_df(ws, dpx, rr_, 0, {c: f3 for c in dpx.columns if c not in ("Scope", "Group", "Team-matches")}) + 1
    ws.write(rr_, 0, "(ii) Real Madrid IRR with and without discipline terms (same discipline-complete sample)", f_h3); rr_ += 1
    dgx = dg.rename(columns={"scope": "Scope", "model": "Model", "n_team_matches": "n team-matches", "rm_irr": "RM IRR", "irr_ci_low": "95% CI low", "irr_ci_high": "95% CI high",
                             "p_value": "p", "aic": "AIC", "pearson_dispersion": "Dispersion"})
    rr_ = put_df(ws, dgx, rr_, 0, {c: f3 for c in dgx.columns if c not in ("Scope", "Model", "n team-matches")}) + 1
    ws.write(rr_, 0, "(iii) Coefficients of the full model", f_h3); rr_ += 1
    dcx = dcf.rename(columns={"scope": "Scope", "variable": "Variable", "coef": "Coef", "irr": "IRR", "ci_low": "95% CI low", "ci_high": "95% CI high", "p_value": "p"})
    rr_ = put_df(ws, dcx, rr_, 0, {c: f3 for c in dcx.columns if c not in ("Scope", "Variable")}) + 1
    ws.write(rr_, 0, "(iv) Leave-Real-Madrid-out forecast with discipline + PPDA", f_h3); rr_ += 1
    dfx = dfc.rename(columns={"scope": "Scope", "model_trained_on_other_teams": "Model trained on other teams", "rm_matches": "RM matches", "rm_observed": "RM observed", "rm_expected": "RM expected",
                              "expected_p2_5": "Expected 2.5%", "expected_p97_5": "Expected 97.5%", "excess": "Excess", "obs_over_expected": "Obs / expected", "p_value_obs_or_more": "p (obs or more)", "dispersion_used": "Dispersion"})
    rr_ = put_df(ws, dfx, rr_, 0, {"RM expected": f1, "Excess": f1, "Obs / expected": f2, "p (obs or more)": fpv, "Dispersion": f2}) + 1
    ws.write(rr_, 0, "(v) Where does the excess come from? Nullified goals per match by VAR reason, Real Madrid vs other teams", f_h3); rr_ += 1
    rsx = rrt.rename(columns={"scope": "Scope", "reason": "Reason", "rm_nullified": "RM nullified", "rm_per_match": "RM / match", "others_nullified": "Others nullified", "others_per_match": "Others / match",
                              "rate_ratio": "Rate ratio", "rr_ci_low": "95% CI low", "rr_ci_high": "95% CI high", "p_one_sided": "p (one-sided)"})
    rr_ = put_df(ws, rsx, rr_, 0, {"RM / match": f3, "Others / match": f3, "Rate ratio": f2, "95% CI low": f2, "95% CI high": f2, "p (one-sided)": fpv}) + 1
    ws.merge_range(rr_, 0, rr_, 12, f"Reading: Real Madrid fouls less and is booked less than other teams, yet its nullified-goal rate is higher; adding fouls (total and attacking half), yellow and red cards does not absorb the effect (IRR {dg_ref.rm_irr:.2f} -> {dg_full.rm_irr:.2f} all teams, {dg_full10.rm_irr:.2f} top-10; expected ~{df_all.rm_expected:.0f} vs {int(df_all.rm_observed)} observed). None of the discipline coefficients is significant at 5%; yellow cards are weakly positive (IRR ~1.07 per card, p~0.1). The negative team-level correlation with fouls reflects possession-dominant teams (fewer fouls, more attacks) rather than discipline causing nullified goals. By reason, offside drives the Real Madrid excess ({int(rs_off.rm_nullified)} of 50, {rs_off.rate_ratio:.1f}x others); attacking-foul and handball nullifications are only 6 each (rate ratios ~2.6-2.7 with wide intervals).", f_note); ws.set_row(rr_, 75); rr_ += 2
    ws.merge_range(rr_, 0, rr_, 12, "H. What would settle the remaining ~2x residual (not available publicly)", f_h2); rr_ += 1
    for line in ["1. Tracking/semi-automated offside data (offside-line position and player at pass): tests the 'runners-in-behind' profile hypothesis.",
                 "2. RFEF/CTA audits of each VAR intervention with a correct/incorrect label: gives the error rate by beneficiary (the only direct test of favouritism).",
                 "3. All VAR *checks* (not only overturns): the denominator for 'overturn rate per review' by team.",
                 "4. VAR-room officials per match: lets us test VAR-official effects separately from the on-field referee."]:
        ws.merge_range(rr_, 0, rr_, 12, line, f_txt); rr_ += 1

    # ============================================================ 7 EDA
    ws = wb.add_worksheet("7_RM_EDA"); xw.sheets["7_RM_EDA"] = ws
    ws.set_column(0, 0, 36); ws.set_column(1, 12, 13)
    ws.write(0, 0, "EDA - Real Madrid's nullified goals in context", f_title)
    rr_ = 2
    pts_lost = int(r.points_lost.sum()); chg = int(r.result_changed.sum())
    ws.merge_range(rr_, 0, rr_, 8, f"Impact: {len(r)} goals nullified in {r.fs_id.nunique()} matches; if all had stood Real Madrid would have gained {pts_lost} points across {chg} matches (counterfactual per goal, ignoring knock-on effects). Opponents had {int(led_rm.opp_nullified_against_them)} goals nullified against Real Madrid, worth {led_rm.points_kept:.0f} points kept by Real Madrid.", f_warn); ws.set_row(rr_, 45); rr_ += 2
    positions = []
    for name, df_ in eda.items():
        ws.write(rr_, 0, name, f_h3); rr_ += 1
        pos0 = rr_
        rr_ = put_df(ws, df_, rr_, 0, {"% of total": fp}) + 1
        positions.append((name, pos0, len(df_)))
    chart_names = ("By reason (Flashscore)", "By half", "By 15-minute window", "By context category")
    for k_, (name, pos0, n_) in enumerate([p for p in positions if p[0] in chart_names]):
        ch = wb.add_chart({"type": "column" if name != "By context category" else "bar"})
        ch.add_series({"name": name, "categories": ["7_RM_EDA", pos0 + 1, 0, pos0 + n_, 0], "values": ["7_RM_EDA", pos0 + 1, 1, pos0 + n_, 1], "fill": {"color": "#1F3864"}})
        ch.set_title({"name": "RM nullified goals - " + name.lower()}); ch.set_legend({"none": True}); ch.set_size({"width": 430, "height": 250})
        ws.insert_chart(4 + (k_ // 2) * 14, 4 + (k_ % 2) * 6, ch)
    ws.write(rr_, 0, "RM per season: attack volume vs nullified goals", f_h3)
    sc = season_cmp.copy()
    sc["RM nullified per 100 goal events"] = (100 * rm_ts.dis / (rm_ts.goals + rm_ts.dis)).values
    put_df(ws, sc, rr_ + 1, 0, {"RM nullified per 38 matches": f1, "Avg other top-10 team (per 38 matches)": f1, "RM nullified per 100 goal events": f1, "RM xG": f1})

    # ============================================================ 8 Referees
    ws = wb.add_worksheet("8_Referees"); xw.sheets["8_Referees"] = ws
    ws.set_column(0, 0, 34); ws.set_column(1, 10, 14)
    ws.write(0, 0, "Referees: Real Madrid's nullified goals vs the same referee's other matches", f_title)
    ws.write(1, 0, "Referee = on-field referee of the match (Transfermarkt). The VAR-room official is not available. 'Others per team-match' = nullified goals per team-match for all non-RM teams under that referee.", f_note)
    rf = ref.rename(columns={"referee": "Referee", "rm_matches": "RM matches", "rm_nullified": "RM nullified", "rm_offsides": "RM offsides", "other_team_matches": "Other team-matches (same ref)",
                             "other_nullified": "Other teams nullified (same ref)", "rm_per_match": "RM nullified / match", "others_per_team_match_same_ref": "Others / team-match (same ref)",
                             "ratio_rm_vs_others_same_ref": "Ratio RM / others"})
    end = put_df(ws, rf, 3, 0, {"RM nullified / match": f3, "Others / team-match (same ref)": f3, "Ratio RM / others": f2, "RM offsides": f0})
    ws.set_row(3, 45)
    ws.freeze_panes(4, 1)
    ws.write(end + 1, 0, "Small samples per referee (0-8 events): individual ratios are noisy; the useful evidence is the homogeneity test (sheet 6-F) and that the ratio is above 1 for most referees.", f_note)

    # ============================================================ 9 Ledger
    ws = wb.add_worksheet("9_Net_Points_Ledger"); xw.sheets["9_Net_Points_Ledger"] = ws
    ws.set_column(0, 0, 24); ws.set_column(1, 8, 16)
    ws.write(0, 0, "Favouritism ledger: points lost to a team's own nullified goals vs points kept because an opponent's goal was nullified", f_title)
    ws.write(1, 0, "Counterfactual per event: result if the nullified goal had counted (all else equal). Net = points kept - points lost (negative = team is worse off). Not a causal estimate of VAR bias - it measures exposure to nullified goals.", f_note)
    lg = ledger.rename(columns={"team": "Team", "own_nullified": "Own goals nullified", "points_lost": "Points lost", "matches_result_changed": "Matches where result would change",
                                "opp_nullified_against_them": "Opponent goals nullified vs team", "points_kept": "Points kept", "net_points_from_nullified_goals": "Net points"})
    end = put_df(ws, lg, 3, 0, {c: f0 for c in lg.columns if c != "Team"})
    ws.set_row(3, 45)

    # ============================================================ 10 VAR accuracy refs
    ws = wb.add_worksheet("10_VAR_Accuracy_Refs"); xw.sheets["10_VAR_Accuracy_Refs"] = ws
    ws.set_column(0, 0, 28); ws.set_column(1, 1, 16); ws.set_column(2, 2, 70); ws.set_column(3, 3, 60); ws.set_column(4, 4, 55)
    ws.write(0, 0, "VAR accuracy references (task premise: >95%)", f_title)
    ws.write(1, 0, "Hierarchy requested: La Liga -> Premier League -> FIFA. No La Liga-specific accuracy publication could be retrieved and verified from this environment, so the La Liga case is covered by the multi-league peer-reviewed study (which includes Spanish matches among 13 countries) and the fallbacks below.", f_note)
    refs = pd.DataFrame([
        ["Multi-league (13 countries; fallback to La Liga)", "92.1% -> 98.3%", "Spitz, Wagemans, Memmert, Williams, Helsen (2021). 'Video assistant referees (VAR): the impact of technology on decision making in association football referees.' J Sports Sci 39(2):147-153. 2,195 matches, 9,732 VAR checks, 795 reviews; accuracy of the final decision 98.3% vs 92.1% for the initial referee call.", "https://doi.org/10.1080/02640414.2020.1809163 (abstract verified via Europe PMC, PMID 32794432)", "Verified (abstract)"],
        ["Premier League", "~96%", "Premier League/PGMOL claim reported by Sky Sports (8-Feb-2024) 'Premier League claims 96 per cent of referee decisions are correct'. Also reported: 82% before VAR -> 96% (league's own data).", "Sky Sports headline, 8 Feb 2024; World Soccer Talk 11 Feb 2026 (headline level)", "Headline-level (full text not retrieved)"],
        ["FIFA World Cup 2018", "95% -> 99.3%", "FIFA: VAR success rate 99.3% vs 95% for referee calls without VAR (335 incidents checked in group stage, 14 overturned).", "https://en.wikipedia.org/wiki/Video_assistant_referee (cites FIFA)", "Verified (Wikipedia citing FIFA)"],
        ["IFAB experiment report (Jan-2018)", "98.9%", "BBC (22-Jan-2018): 'VAR: Report shows technology has been 98.9% accurate in decision-making' (IFAB/KU Leuven-Belgian FA analysis of 804 matches in 20 competitions).", "BBC Sport, 22 Jan 2018 (headline level)", "Headline-level"],
        ["Spanish refereeing (La Liga context)", "98% of penalties", "El Pais (10-Dec-2020): 'El arbitraje espanol sostiene que con el VAR acierta en el 98% de los penaltis' - claim by Spanish refereeing body.", "El Pais, 10 Dec 2020 (headline level)", "Headline-level"],
        ["Media on Real Madrid & VAR (not used in calculations)", "n/a", "Diario AS (25-Jun-2026): 'Real Madrid vs VAR: a telling story of the video review system and the LaLiga club hurt more than any other'; AS (29-May-2025) 'El VAR bate record: los equipos mas beneficiados y perjudicados'. These are the narratives behind the belief tested here; their methodology was not retrievable.", "Diario AS via Google News (headline level)", "Headline-level, unverified method"],
    ], columns=["Competition / scope", "Accuracy", "Source / what it says", "Link", "Verification status"])
    end = put_df(ws, refs, 3, 0)
    for i in range(len(refs)):
        ws.set_row(4 + i, 75)
    ws.write(end + 1, 0, "How these are used: sheet 6-G stress-tests the claim that VAR error could explain Real Madrid's excess, using 98.3% (peer-reviewed), 96% (Premier League), 95% (task floor), and 90%/80% (deliberately pessimistic).", f_note)

    # ============================================================ 11 Sources / method / limits
    ws = wb.add_worksheet("11_Sources_Method_Limits"); xw.sheets["11_Sources_Method_Limits"] = ws
    ws.set_column(0, 0, 30); ws.set_column(1, 1, 130)
    ws.write(0, 0, "Sources, method and limitations", f_title)
    items = [
        ("SOURCES", None),
        ("Nullified goals", "Flashscore match incident feeds ('Goal Disallowed' with scorer, minute and reason) for all 3,118 La Liga matches 2018-19 to 12-Oct-2026, plus live commentary (VAR wording, decision text). 397 incidents; 394 have explicit VAR evidence (commentary, or ESPN 'Video Review'/overturned log) = primary dataset; 3 do not (none involve Real Madrid)."),
        ("Independent check", "ESPN public API match summaries (3,210 matches): explicit 'GOAL OVERTURNED BY VAR' events (reliable from 2023-24), VAR review delays, offside events naming the offside player (used for passive_player and scorer-vs-teammate offside)."),
        ("Referees", "Transfermarkt match sheets (full names) for every match with a nullified goal plus all Real Madrid matches (617 sheets); Flashscore abbreviated names mapped to full names for the rest."),
        ("Attack volume", "Flashscore match statistics (shots, shots on target, offsides, corners, possession, fouls; all seasons) validated against ESPN box scores (6,068 team-matches, r=0.94-0.98); xG from Understat (all seasons incl. 2026-27) validated against Flashscore xG (r=0.93). Pressing: Understat PPDA components per match (ppda_att = opponent passes in the pressing zone, ppda_def = own defensive actions there; PPDA = att/def), 98% of team-matches covered; the opponent's PPDA is taken from the other team's row of the same match. Discipline: total fouls, yellow and red cards from Flashscore statistics; fouls by pitch zone parsed from ESPN commentary (scripts/09_fouls_espn.py), 6,208 team-matches (99.6% of matches), ~91% of box-score fouls captured."),
        ("League position", "Rebuilt from match results: table before each kick-off, sorted by points, goal difference, goals scored (official head-to-head tie-breaks not applied). Round-1 events have no table."),
        ("Champions / top-10", "From the rebuilt final tables. Top-10 = ten best teams in each season's final table (so relegated teams are excluded). 2026-27: table after 8 rounds."),
        ("METHOD", None),
        ("Definitions", "Nullified goal = goal scored and then ruled out after a VAR review (offside, attacking foul, handball, other). Goals ruled out on the pitch by the assistant referee or referee without a VAR review are NOT in the VAR dataset; they are a separate dataset (sheet 12, scripts/10_onfield_disallowed.py and 11_onfield_events.py) mined from Flashscore commentary for all teams. 'Goal events' = goals + nullified goals."),
        ("Statistics", "Exact conditional Poisson rate tests; Poisson GLM with cluster-robust SE by match; leave-RM-out Monte Carlo forecast (gamma-Poisson draws when dispersion >1); same-match binomial simulation; Fisher exact; chi-square heterogeneity across referees; Pearson/Spearman/Kendall with bootstrap CIs."),
        ("Reproducibility", "scripts/01_crawl_espn.py -> 02_crawl_flashscore.py -> 03_build_dataset.py -> 04_fetch_understat.py -> 06_referees_tm.py -> 05_enrich.py -> 07_analysis.py -> 08_build_excel.py. Raw caches are in data/raw, processed tables in data/processed."),
        ("LIMITATIONS", None),
        ("Tweet reconciliation", "The post's provider/definition is unknown; exact counts cannot be reproduced. Conclusions about direction and magnitude (RM ~1.7-1.9x the runner-up) hold across definitions."),
        ("Event completeness", "Flashscore may miss a few nullified goals in early seasons (2018-19 has the fewest) or record goals ruled out by on-field assistants. Cross-source ESPN corroboration is 73-94% by season (ESPN itself is incomplete before 2023-24)."),
        ("Referee field", "The on-field referee is not the VAR official. The VAR-room referee was not obtainable for most matches."),
        ("Causality", "Counts and rates cannot separate 'attacking profile' from 'systematic treatment'. Tests D-F look for observable fingerprints of bias (within-match asymmetry, referee concentration, opponents spared) and find none; absence of evidence is not proof, especially with 50 events."),
        ("Counterfactual points", "Points lost per goal assume the match would otherwise have unfolded identically; they ignore tactical knock-on effects and multiple nullified goals in one match."),
        ("Your validation sample", "Corrections are in sheet 1-C. Rows 1 (minute), 2 (minute), 3 (not found) and 4 (mixed matches) should be updated."),
    ]
    rr_ = 2
    for k, v in items:
        if v is None:
            ws.merge_range(rr_, 0, rr_, 1, k, f_h2); rr_ += 1; continue
        ws.write(rr_, 0, k, F(bold=True, valign="top")); ws.write(rr_, 1, v, f_txt); ws.set_row(rr_, max(30, 15 * (len(v) // 125 + 1))); rr_ += 1

    # ============================================================ 12 On-field disallowed goals
    ws = wb.add_worksheet("12_OnField_Disallowed"); xw.sheets["12_OnField_Disallowed"] = ws
    ws.set_column(0, 0, 8); ws.set_column(1, 1, 22); ws.set_column(2, 25, 14)
    ws.write(0, 0, "Goals ruled out ON THE PITCH (assistant-referee flag / referee whistle, no VAR review) - why the 26-Oct-2024 Mbappe 65' goal is not in the VAR dataset", f_title)
    ws.merge_range(1, 0, 1, 14, "Definition: a goal that was scored and then chalked off by the on-field officials without any VAR review (commentary lines such as 'The assistant referee raises his flag ... puts the ball into the net, but he is flagged for offside', 'A goal, which was scored by X, was disallowed due to offside', 'Goal disallowed! X scores but the referee blows his whistle for a foul'). Lines mentioning VAR and events within 4 minutes of an existing VAR-confirmed event for the same team are excluded, and the same goal described by several phrasings is counted once. Source: Flashscore live commentary for all 3,118 matches (40-80+ lines per match in every season, so coverage is even). The ESPN feed shows these only as a plain 'Offside' event, so it cannot cross-check them.", f_note)
    ws.set_row(1, 62)
    rr_ = 3
    ws.merge_range(rr_, 0, rr_, 14, "A. The Clasico of 26-Oct-2024 (Real Madrid 0-4 FC Barcelona) - both Mbappe goals", f_h2); rr_ += 1
    clas = pd.DataFrame([
        ["30'", "Kylian Mbappe", "Offside (build-up); VAR review", "YES - 'GOAL OVERTURNED BY VAR' (ESPN) / Goal Disallowed (Flashscore)", "Included: rank 33 in sheet 2 and in the 50-goal VAR dataset"],
        ["65'-66'", "Kylian Mbappe", "Offside; assistant referee flag, whistle", "NO - no VAR review in Flashscore or ESPN; ESPN logs only 'Offside, Real Madrid. Kylian Mbappe is caught offside' at 66'", "Not a VAR nullification. Listed here in the on-field dataset"],
    ], columns=["Minute", "Player", "Decision", "VAR involved?", "Treatment"])
    rr_ = put_df(ws, clas, rr_, 0) + 1
    ws.write(rr_, 0, "Earlier draft of your validated file, row 51 (2024-10-26 Mbappe 65', since removed) - fields that would have needed correcting for a VAR dataset", f_h3); rr_ += 1
    fix = pd.DataFrame([
        ["coach", "Jose Mourinho", "Carlo Ancelotti", "Ancelotti was the coach in 2024-25 (row 33, the 30' goal of the same match, has Ancelotti)"],
        ["half", "first", "second", "65'/66' is in the second half"],
        ["score_before_goal (team-opp)", "2-0", "0-2", "Barcelona already led 2-0 (Lewandowski 54' and 56'); orientation is Real Madrid - rival"],
        ["what_the_goal_would_have_been", "Go-ahead / opener", "Reduce deficit", "0-2 -> 1-2"],
        ["var_decision_text / var_evidence", "'The referee looks satisfied after his VAR review...' / Explicit VAR wording", "Assistant referee flag, no VAR review", "The text was copied from the 30' event. Suggest a new var_reason value such as 'Offside (on-field, no VAR)' so these are not mixed into VAR counts"],
        ["minute", "65", "65-66", "Shot saved at 64'; goal and flag at 65'-66' (feeds: 65:25 clock; 66' display)"],
        ["points_lost_due_to_nullification", "0", "0", "Real Madrid lost 0-4 either way"],
    ], columns=["Column", "Currently", "Should be", "Why"])
    rr_ = put_df(ws, fix, rr_, 0) + 2
    ws.merge_range(rr_, 0, rr_, 14, f"B. Does Real Madrid stand out for goals ruled out on the pitch? ({on_tot} events, all teams, 2018-19 to 12-Oct-2026)", f_h2); rr_ += 1
    tt = ont.head(15).rename(columns={"team": "Team", "matches": "Matches", "var_nullified": "VAR-nullified", "onfield": "Ruled out on the pitch", "combined": "Combined",
                                      "goals": "Goals scored", "onfield_per_match": "On-field / match", "combined_per_match": "Combined / match",
                                      "share_of_combined_that_was_var_pct": "% of combined that was VAR", "rank_combined": "Rank: combined", "rank_onfield": "Rank: on-field", "rank_var": "Rank: VAR"})
    rr_ = put_df(ws, tt, rr_, 0, {"On-field / match": f3, "Combined / match": f3, "% of combined that was VAR": f1}) + 1
    ws.set_row(rr_ - len(tt) - 1, 40)
    ws.merge_range(rr_, 0, rr_, 14, "Reading: Real Madrid is first in all three, but on-field disallowed goals are close to Barcelona (28), Atletico (27) and Villarreal (26). These are decisions by the officials on the pitch with no VAR involvement, so the Real Madrid excess is not a VAR-only phenomenon.", f_note); rr_ += 2
    ws.write(rr_, 0, "Rate tests: Real Madrid vs other teams (exact conditional Poisson test)", f_h3); rr_ += 1
    orx = onr.rename(columns={"scope": "Scope", "category": "Category", "exposure": "Exposure", "rm_events": "RM events", "rm_rate": "RM rate", "others_events": "Others events",
                              "others_rate": "Others rate", "rate_ratio": "Rate ratio", "rr_ci_low": "95% CI low", "rr_ci_high": "95% CI high", "p_one_sided": "p (one-sided)"})
    rr_ = put_df(ws, orx, rr_, 0, {"RM rate": f3, "Others rate": f3, "Rate ratio": f2, "95% CI low": f2, "95% CI high": f2, "p (one-sided)": fpv}) + 1
    ws.write(rr_, 0, "Poisson regression: Real Madrid IRR for on-field and combined counts", f_h3); rr_ += 1
    ogx = ong.rename(columns={"scope": "Scope", "category": "Category", "model": "Model", "rm_irr": "RM IRR", "irr_ci_low": "95% CI low", "irr_ci_high": "95% CI high", "p_value": "p"})
    rr_ = put_df(ws, ogx, rr_, 0, {c: f3 for c in ogx.columns if c not in ("Scope", "Category", "Model")}) + 1
    ws.write(rr_, 0, "Is the VAR stage different from the on-field stage for Real Madrid? (stacked counts, RM x VAR interaction; ratio > 1 would mean VAR adds a Real Madrid-specific excess)", f_h3); rr_ += 1
    oix = oni.rename(columns={"scope": "Scope", "model": "Model", "term": "Term", "irr": "IRR", "ci_low": "95% CI low", "ci_high": "95% CI high", "p_value": "p"})
    rr_ = put_df(ws, oix, rr_, 0, {c: f3 for c in oix.columns if c not in ("Scope", "Model", "Term")}) + 1
    ws.merge_range(rr_, 0, rr_, 14, f"Reading: the interaction is {on_int.irr:.2f}x with a 95% CI of {on_int.ci_low:.2f}-{on_int.ci_high:.2f} (p={on_int.p_value:.2f}). The point estimate is above 1, so a modest VAR-specific effect cannot be ruled out with {rm_n} VAR events, but the data do not show one, and the excess already exists before VAR is involved.", f_note); rr_ += 2
    ws.merge_range(rr_, 0, rr_, 14, f"C. Real Madrid goals ruled out on the pitch (n = {on_rm_n})", f_h2); rr_ += 1
    rmx = onf_ev[onf_ev.team == RM].drop(columns=["fs_id", "team", "kind", "season_final_pos"]).copy()
    rmx["date"] = rmx.date.dt.normalize()
    rmx.insert(0, "n", range(1, len(rmx) + 1))
    rmx = rmx.drop(columns=["rank"])
    rmx = rmx[["n", "date", "season", "round", "rival", "active_player", "local_flag", "reason", "minute", "minute_display", "half", "score_before_goal", "goal_would_have_been",
               "team_goals_final", "rival_goals_final", "outcome", "points_lost", "league_position_at_time", "rival_position_at_time", "points_at_time", "referee_on_field", "commentary"]]
    ws.set_column(5, 5, 20); ws.set_column(20, 20, 26); ws.set_column(21, 21, 90)
    end = put_df(ws, rmx, rr_, 0, {"round": f0, "minute": f0, "league_position_at_time": f0, "rival_position_at_time": f0, "points_at_time": f0})
    ws.set_row(rr_, 40)
    rr_ = end + 2
    ws.merge_range(rr_, 0, rr_, 14, f"D. All teams: goals ruled out on the pitch (n = {on_tot})", f_h2); rr_ += 1
    allx = onf_ev.drop(columns=["fs_id", "kind", "season_final_pos"]).copy()
    allx["date"] = allx.date.dt.normalize()
    allx = allx[["rank", "date", "season", "round", "team", "rival", "active_player", "local_flag", "reason", "minute", "minute_display", "half", "score_before_goal", "goal_would_have_been",
                 "team_goals_final", "rival_goals_final", "outcome", "points_lost", "league_position_at_time", "rival_position_at_time", "points_at_time", "referee_on_field", "commentary"]]
    put_df(ws, allx, rr_, 0, {"round": f0, "minute": f0, "league_position_at_time": f0, "rival_position_at_time": f0, "points_at_time": f0})
    ws.set_row(rr_, 40)

    # ============================================================ 13 Players, games affected, champion vs not, title scenarios
    ws = wb.add_worksheet("13_Titles_Players_Games"); xw.sheets["13_Titles_Players_Games"] = ws
    ws.set_column(0, 0, 30); ws.set_column(1, 14, 15)
    ws.write(0, 0, "Player concentration, matches affected, champion vs not champion, and title scenario analysis (Real Madrid VAR-nullified goals)", f_title)
    if not HAVE_EDA:
        ws.write(2, 0, "Run 'Real Madrid VAR - EDA.ipynb' first: it exports the eda_*.csv tables this sheet reads.", f_warn)
    else:
        from PIL import Image

        def add_img(r0, name, scale=0.42):
            p = os.path.join(FIGD, name)
            if not os.path.exists(p):
                return r0
            w_, h_ = Image.open(p).size
            ws.insert_image(r0, 0, p, {"x_scale": scale, "y_scale": scale})
            return r0 + int(h_ * scale / 20) + 2

        ws.merge_range(1, 0, 1, 12, "Source: tables exported by the EDA notebook (data/processed/eda_*.csv) and its figures (figures/*.png). All figures use VAR-confirmed nullified goals (50 Real Madrid goals in 44 matches). The same charts, plus more, are in the notebook.", f_note)
        rr_ = 3
        # ---------------- Q1
        ws.merge_range(rr_, 0, rr_, 12, f"Q1. Concentration by player: {e_k75} of {len(e_pc)} players account for 75% of the incidents", f_h2); rr_ += 1
        q1 = pd.DataFrame({"Player": e_pc.index, "Nullified goals": e_pc.values, "% of total": (100 * e_pc / e_pc.sum()).values, "Cumulative %": (100 * e_cum).values})
        q1["In the 75% group"] = ["yes" if i < e_k75 else "" for i in range(len(q1))]
        rr_ = put_df(ws, q1, rr_, 0, {"% of total": f1, "Cumulative %": f1}) + 1
        ws.merge_range(rr_, 0, rr_, 12, "Reading: goals are attributed to the player whose goal was ruled out. Benzema and Mbappe lead with 8 each; the rest of the front line shares the remainder, so there is no single-player story (top-3 share 40%, in line with other teams).", f_note); rr_ += 2
        rr_ = add_img(rr_, "03_player_pareto.png")
        # ---------------- Q2
        n_m = len(e_g)
        ws.merge_range(rr_, 0, rr_, 12, f"Q2. Matches directly affected: {n_m} matches with a nullified goal, {e_dl} ended in a draw or loss, {e_chg} would have changed result", f_h2); rr_ += 1
        out_ct = e_g.groupby("outcome").agg(matches=("fs_id", "size"), nullified_goals=("nullified", "sum")).reindex(["WIN", "DRAW", "LOSS"]).reset_index().rename(
            columns={"outcome": "Final result", "matches": "Matches", "nullified_goals": "Nullified goals"})
        rr_ = put_df(ws, out_ct, rr_, 0) + 1
        chg_ct = pd.crosstab(e_g.outcome, e_g.result_change).reindex(["WIN", "DRAW", "LOSS"]).reset_index().rename(columns={"outcome": "Final result"})
        ws.write(rr_, 0, "Would the result have changed if all nullified goals counted?", f_h3); rr_ += 1
        rr_ = put_df(ws, chg_ct, rr_, 0) + 1
        sm = pd.DataFrame({"Measure": ["Real Madrid nullified goals", "Matches with a nullified goal", "...ended in a draw or loss", "...result would have changed (loss to draw, draw to win)", "Points that would have been gained"],
                           "Count": [int(e_pc.sum()), n_m, e_dl, e_chg, e_pts],
                           "% of the matches with a nullified goal": [np.nan, 100.0, 100 * e_dl / n_m, 100 * e_chg / n_m, np.nan]})
        rr_ = put_df(ws, sm, rr_, 0, {"% of the matches with a nullified goal": f1}) + 1
        ws.write(rr_, 0, "Matches where the result would have changed", f_h3); rr_ += 1
        chg_tbl = e_g[e_g.result_change != "No change"][["date", "season", "rival", "venue", "gf", "ga", "nullified", "reasons", "result_change", "points_lost"]].rename(
            columns={"date": "Date", "season": "Season", "rival": "Rival", "venue": "Venue", "gf": "RM goals", "ga": "Rival goals", "nullified": "Nullified goals", "reasons": "Reason", "result_change": "Result change", "points_lost": "Points"})
        chg_tbl["Date"] = chg_tbl.Date.dt.normalize()
        rr_ = put_df(ws, chg_tbl, rr_, 0) + 1
        ws.write(rr_, 0, "All 44 matches with a nullified goal", f_h3); rr_ += 1
        all_tbl = e_g[["date", "season", "rival", "venue", "gf", "ga", "outcome", "nullified", "reasons", "result_change", "points_lost"]].rename(
            columns={"date": "Date", "season": "Season", "rival": "Rival", "venue": "Venue", "gf": "RM goals", "ga": "Rival goals", "outcome": "Result", "nullified": "Nullified goals", "reasons": "Reason", "result_change": "Result change", "points_lost": "Points"})
        all_tbl["Date"] = all_tbl.Date.dt.normalize()
        rr_ = put_df(ws, all_tbl, rr_, 0) + 1
        rr_ = add_img(rr_, "06_games_affected.png", 0.38)
        # ---------------- Q3
        ws.merge_range(rr_, 0, rr_, 12, "Q3. Nullified goals when Real Madrid was champion vs not champion", f_h2); rr_ += 1
        sst = e_ss.rename(columns={"season": "Season", "status": "Status", "rm_final_pos": "RM final position", "rm_points": "RM points", "league_champion": "League champion", "matches": "Matches",
                                   "nullified": "Nullified goals", "per_match": "Per match", "per_38": "Per 38 matches", "points_lost_if_counted": "Points if counted", "matches_with_nullified": "Matches with nullified"})
        rr_ = put_df(ws, sst, rr_, 0, {"Per match": f3, "Per 38 matches": f1}) + 1
        gq = e_grp.reset_index().rename(columns={"status": "Status", "seasons": "Seasons", "matches": "Matches", "nullified": "Nullified goals", "points_lost": "Points if counted", "matches_with_nullified": "Matches with nullified"})
        gq["% of all RM nullified goals"] = 100 * gq["Nullified goals"] / gq["Nullified goals"].sum()
        gq["% of RM matches"] = 100 * gq.Matches / gq.Matches.sum()
        gq["Per match"] = gq["Nullified goals"] / gq.Matches
        gq["Per 38 matches"] = gq["Per match"] * 38
        from scipy import stats as _st
        gq["95% CI low (per 38)"] = [_st.chi2.ppf(.025, 2 * n) / 2 / m * 38 for n, m in zip(gq["Nullified goals"], gq.Matches)]
        gq["95% CI high (per 38)"] = [_st.chi2.ppf(.975, 2 * (n + 1)) / 2 / m * 38 for n, m in zip(gq["Nullified goals"], gq.Matches)]
        ws.write(rr_, 0, "By status (2026-27 is partial and shown separately)", f_h3); rr_ += 1
        rr_ = put_df(ws, gq, rr_, 0, {"% of all RM nullified goals": f1, "% of RM matches": f1, "Per match": f3, "Per 38 matches": f1, "95% CI low (per 38)": f1, "95% CI high (per 38)": f1}) + 1
        ch_, nc_ = gq.set_index("Status").loc["Champion"], gq.set_index("Status").loc["Not champion"]
        bt_ = _st.binomtest(int(ch_["Nullified goals"]), int(ch_["Nullified goals"] + nc_["Nullified goals"]), ch_.Matches / (ch_.Matches + nc_.Matches))
        ws.merge_range(rr_, 0, rr_, 12, f"Reading: champion seasons {ch_['Per 38 matches']:.1f} per 38 matches vs {nc_['Per 38 matches']:.1f} in non-title seasons (rate ratio {ch_['Per match'] / nc_['Per match']:.2f}, exact two-sided p = {bt_.pvalue:.2f}): lower in title seasons but not statistically significant; 2022-23 (11 goals) and 2024-25 (9 goals) drive the non-title figure.", f_note); rr_ += 2
        rr_ = add_img(rr_, "07_champion_vs_not.png", 0.4)
        # ---------------- Q4
        ws.merge_range(rr_, 0, rr_, 12, "Q4. Title scenario analysis: would the nullified goals have changed a La Liga title?", f_h2); rr_ += 1
        ws.merge_range(rr_, 0, rr_, 12, "Method: every season is rebuilt from all 380 match results and sorted with the La Liga tie-break (points, head-to-head points, head-to-head goal difference, goal difference, goals scored). Goals are added back to the affected matches and the WHOLE table is recomputed, so opponents lose the points Real Madrid gains. A = all 50 Real Madrid VAR-nullified goals (upper bound: assumes every nullification was wrong); B = every team's VAR-nullified goals (a world with no VAR goal-nullifications); C = A plus goals ruled out on the pitch without VAR (extreme upper bound, sensitivity).", f_note); ws.set_row(rr_, 62); rr_ += 1
        scen_order = ["Actual", "A. Real Madrid only (VAR)", "B. Everyone (VAR)", "C. Real Madrid only (VAR + on-field)"]
        for val, ttl, fm in (("rm_pos", "Real Madrid league position", f0), ("rm_pts", "Real Madrid points", f0), ("champion", "League champion", None), ("lead_over_best_rival", "Real Madrid points minus best rival (0 = level on points)", f0)):
            ws.write(rr_, 0, ttl, f_h3); rr_ += 1
            pv = e_sc.pivot(index="season", columns="scenario", values=val)[scen_order].reset_index().rename(columns={"season": "Season"})
            rr_ = put_df(ws, pv, rr_, 0, {c: fm for c in scen_order} if fm else None) + 1
        ws.set_column(1, 4, 24)
        rr_ = add_img(rr_, "08_title_scenarios_gap.png", 0.4)
        ws.write(rr_, 0, "Full re-ranked leaderboards (top 6): actual vs scenario A, seasons where Real Madrid did not win the title", f_h3); rr_ += 1
        act_ch = e_sc[e_sc.scenario == "Actual"].set_index("season").champion
        for s in [x for x in sorted(e_lb.season.unique()) if x != "2026-27" and act_ch.get(x) != "Real Madrid"]:
            a = e_lb[(e_lb.season == s) & (e_lb.scenario == "Actual")][["pos", "team", "pts", "gd"]].rename(columns={"pos": "Pos (actual)", "team": "Team (actual)", "pts": "Pts (actual)", "gd": "GD (actual)"}).reset_index(drop=True)
            b = e_lb[(e_lb.season == s) & (e_lb.scenario == "A. Real Madrid only (VAR)")][["pos", "team", "pts", "gd"]].rename(columns={"pos": "Pos (A)", "team": "Team (A)", "pts": "Pts (A)", "gd": "GD (A)"}).reset_index(drop=True)
            ws.write(rr_, 0, f"{s} (champion: {act_ch[s]})", F(bold=True, font_color="#1F3864"))
            rr_ = put_df(ws, pd.concat([a, b], axis=1), rr_ + 1, 0, {c: f0 for c in ("Pos (actual)", "Pts (actual)", "GD (actual)", "Pos (A)", "Pts (A)", "GD (A)")}) + 1
        rr_ = add_img(rr_, "09_title_scenarios_top4.png", 0.3)
        ws.write(rr_, 0, "Break-even: how many nullified goals would have had to be WRONG for Real Madrid to win the title?", f_h3); rr_ += 1
        be_t = e_be.rename(columns={"season": "Season", "champion": "Champion", "gap_pts": "Gap (pts)", "rm_nullified_goals": "RM nullified goals", "max_points_recoverable": "Max points recoverable",
                                    "min_wrong_calls_to_level": "Min wrong calls to be level", "min_wrong_calls_to_lead": "Min wrong calls to lead", "rm_wins_head_to_head_tiebreak": "RM wins head-to-head tie-break",
                                    "h2h_points_rm_vs_champion": "Head-to-head points (RM-champion)", "rm_champion_if_all_goals_counted": "RM champion if all counted",
                                    "expected_wrong_calls_at_98pct_accuracy": "Expected wrong calls at 98% accuracy", "at_95pct": "Expected wrong calls at 95% accuracy"})
        rr_ = put_df(ws, be_t, rr_, 0, {"Expected wrong calls at 98% accuracy": f2, "Expected wrong calls at 95% accuracy": f2}) + 1
        ws.set_row(rr_ - len(be_t) - 1, 45)
        ws.write(rr_, 0, "Monte-Carlo: probability that Real Madrid would have been champion if each nullified goal was wrong with probability p (20,000 simulations; level on points settled by head-to-head)", f_h3); rr_ += 1
        mcp = e_mc.pivot(index="season", columns="p_wrong", values="p_rm_champion").mul(100).reset_index()
        mcp.columns = ["Season"] + [f"p wrong = {c:.1%}" for c in mcp.columns[1:]]
        rr_ = put_df(ws, mcp, rr_, 0, {c: f1 for c in mcp.columns[1:]}) + 1
        ws.merge_range(rr_, 0, rr_, 12, f"Reading: only 2020-21 can flip. At the realistic 1.7%-5% VAR error rates the chance is {e_mc[e_mc.p_wrong == 0.017].p_rm_champion.max():.1%}-{e_mc[e_mc.p_wrong == 0.05].p_rm_champion.max():.1%}; even if 1 in 4 nullifications were wrong it is {e_mc[e_mc.p_wrong == 0.25].p_rm_champion.max():.0%}. Every other season stays at 0% because the gap (6-18 pts, or 1-2 pts in 2022-23 and 2024-25) cannot be closed by Real Madrid's own nullified goals.", f_note); ws.set_row(rr_, 45); rr_ += 2
        rr_ = add_img(rr_, "10_title_monte_carlo.png", 0.38)
        ws.merge_range(rr_, 0, rr_, 12, "Interpretation: counting EVERY Real Madrid nullified goal as wrong (scenario A) changes one title (2020-21, level on points and ahead on head-to-head); in the neutral league-wide scenario B Real Madrid gains 2022-23 but loses 2023-24, so the effects roughly offset. These scenarios do not prove the decisions were wrong: with VAR accuracy of 96-98% almost all were correct. Counterfactuals ignore knock-on effects on how the matches would have unfolded.", f_note); ws.set_row(rr_, 62)

    wb.get_worksheet_by_name("Summary").activate()

print("written", XLSX)
RM_B.to_csv(os.path.join(P, "RM_nullified_goals_breakdown.csv"), index=False, encoding="utf-8-sig")
