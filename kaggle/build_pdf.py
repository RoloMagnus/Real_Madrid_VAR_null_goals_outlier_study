"""Build the Kaggle companion PDF from the tables written by reproduce.py.

    python kaggle/reproduce.py && python kaggle/make_figures.py && python kaggle/data_dictionary.py && python kaggle/build_pdf.py
"""
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
                                Preformatted)

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
FIG = OUT / "figures"
PDF = HERE / "Real_Madrid_VAR_null_goals_Kaggle.pdf"
NAVY, RED, LIGHT, GRID = colors.HexColor("#1F3864"), colors.HexColor("#C00000"), colors.HexColor("#EEF1F7"), colors.HexColor("#B8C0D0")

fd = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
for n, f in (("DV", "DejaVuSans.ttf"), ("DV-B", "DejaVuSans-Bold.ttf"), ("DV-I", "DejaVuSans-Oblique.ttf"), ("DVM", "DejaVuSansMono.ttf")):
    pdfmetrics.registerFont(TTFont(n, str(fd / f)))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-B")

BASE = ParagraphStyle("b", fontName="DV", fontSize=8.6, leading=12, alignment=TA_JUSTIFY, spaceAfter=5)
H1 = ParagraphStyle("h1", parent=BASE, fontName="DV-B", fontSize=13, leading=16, textColor=NAVY, spaceBefore=10, spaceAfter=6, alignment=0, keepWithNext=1)
H2 = ParagraphStyle("h2", parent=BASE, fontName="DV-B", fontSize=10, leading=13, textColor=NAVY, spaceBefore=7, spaceAfter=4, alignment=0, keepWithNext=1)
TITLE = ParagraphStyle("t", parent=BASE, fontName="DV-B", fontSize=17, leading=21, textColor=NAVY, alignment=0, spaceAfter=6)
SUB = ParagraphStyle("s", parent=BASE, fontSize=9, textColor=colors.HexColor("#444444"), alignment=0)
CELL = ParagraphStyle("c", parent=BASE, fontSize=7.4, leading=9.2, alignment=0, spaceAfter=0)
CELLB = ParagraphStyle("cb", parent=CELL, fontName="DV-B")
SMALL = ParagraphStyle("sm", parent=BASE, fontSize=7.4, leading=9.5, textColor=colors.HexColor("#444444"), alignment=0)
BOX = ParagraphStyle("box", parent=BASE, backColor=LIGHT, borderColor=GRID, borderWidth=0.6, borderPadding=6, spaceBefore=4, spaceAfter=9)
CODE = ParagraphStyle("code", fontName="DVM", fontSize=5.7, leading=7.0, backColor=colors.HexColor("#F6F6F6"), borderPadding=4)


def P(t, st=BASE):
    return Paragraph(t, st)


def esc(x):
    return escape(str(x))


def table(rows, widths, header=True, style=CELL, zebra=True, extra=()):
    data = [[c if not isinstance(c, str) else Paragraph(c, CELLB if (header and i == 0) else style)
             for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, GRID),
          ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("LINEBELOW", (0, 0), (-1, 0), 0.8, NAVY)]
    if zebra:
        st += [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F8F9FC")) for i in range(2, len(rows), 2)]
    t.setStyle(TableStyle(st + list(extra)))
    t.spaceAfter = 7
    return t


def fig(name, width):
    from PIL import Image as PI
    w, h = PI.open(FIG / name).size
    return Image(str(FIG / name), width=width, height=width * h / w)


f2 = lambda x: f"{x:.2f}"
ci = lambda a, b: f"{a:.2f}\u2013{b:.2f}"


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("DV", 7)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(1.8 * cm, 1.1 * cm, "Real Madrid and recorded VAR-nullified goals \u00b7 Kaggle companion document \u00b7 observational analysis of public feeds")
    canvas.drawRightString(A4[0] - 1.8 * cm, 1.1 * cm, f"Page {doc.page}")
    canvas.restoreState()


def source_of(func_names):
    src = (HERE / "reproduce.py").read_text(encoding="utf-8")
    out = []
    for fn in func_names:
        m = re.search(rf"^def {fn}\(.*?(?=^def |^# -----|\Z)", src, re.S | re.M)
        out.append(m.group(0).rstrip())
    return "\n\n".join(out)


def main():
    H = json.loads((OUT / "headline.json").read_text(encoding="utf-8"))
    rd = lambda n: pd.read_csv(OUT / f"{n}.csv", encoding="utf-8-sig")
    ds, es, lo, ce, cmx = rd("definition_sensitivity"), rd("estimator_sensitivity"), rd("leave_one_season_out"), rd("club_adjusted_effects"), rd("classification_mix")
    ab, ts, mc, rh, pv, pw = rd("ascertainment_what_if"), rd("title_fixed_score_scenario"), rd("title_assumed_error_scenarios"), rd("referee_heterogeneity"), rd("post_vs_reconstruction"), rd("audit_power")
    dd = pd.read_csv(HERE / "data_dictionary.csv", encoding="utf-8-sig")
    tier = {r.item[:2]: r for r in cmx.itertuples() if r.item[:2] in ("T1", "T2", "T3")}
    rng_all = pd.concat([ds.adj_irr, es.irr, lo.irr])
    def_min, def_max = ds.adj_irr.min(), ds.adj_irr.max()
    rm_club = ce[ce.team == "Real Madrid"].iloc[0]
    second = ce.iloc[1]
    chi_p = re.search(r"p = ([\d.]+)", rh.detail.iloc[0]).group(1)
    pow05 = rh[rh.item.str.contains("SD 0.5")].value.iloc[0]
    s2 = ds[ds.key == "S2"].iloc[0]
    d3 = ds[ds.key == "D3"].iloc[0]
    t2021 = ts[ts.season == "2020-21"].iloc[0]
    mc2021 = mc[mc.season == "2020-21"].set_index("assumed_error_probability").p_rm_champion

    st = []
    A = st.append
    # ------------------------------------------------------------------ title and abstract
    A(P("Real Madrid and recorded VAR-nullified goals in La Liga, 2018-19 to October 2026", TITLE))
    A(P("Kaggle companion: revised abstract, inclusion rules, data dictionary, reproducible code and sensitivity analyses", ParagraphStyle("s2", parent=SUB, fontName="DV-B", fontSize=10, leading=13)))
    A(P("Version of 13 October 2026 \u00b7 Scope: La Liga league matches, eight complete seasons (2018-19 to 2025-26) plus the first eight rounds of 2026-27, "
        "up to 12 October 2026 \u00b7 Code and data: github.com/RoloMagnus/Real_Madrid_VAR_null_goals_outlier_study (folder <font name='DVM'>kaggle/</font>). "
        "This document supplements, and does not replace, the article draft in <font name='DVM'>article/</font>, whose text is unchanged.", SUB))
    A(Spacer(1, 6))
    A(P("Abstract", H1))
    A(P(f"On 10 October 2026 a widely shared post listed the La Liga clubs with the most goals ruled out by VAR since 2018 and gave Real Madrid 42 (+1 that day). "
        f"The post does not state its definition, data source or cut-off. We rebuilt event data from four public sources for all 3,118 league matches played "
        f"in eight complete seasons plus part of 2026-27 and asked whether Real Madrid's recorded count stays elevated after adjusting for exposure and attacking "
        f"activity, and how much the answer depends on the event definition and on how events are recorded.", BASE))
    A(P(f"Under our inclusion rules we record {H['rm_events']} VAR-nullified goals for Real Madrid and {H['next_team_events']} for the next club ({H['next_team']}): "
        f"{H['rm_rate']:.3f} per team-match against {H['others_rate']:.3f} for all other clubs (rate ratio {f2(H['rate_ratio'])}, 95% CI {ci(H['rr_lo'], H['rr_hi'])}). "
        f"Our reconstruction produces a different count from the post's; because the post's definition and cut-off are not known, we do not regard either count as the "
        f"correct one. We count a goal that was scored and then ruled out with VAR involvement evident in a public feed. Of Real Madrid's 50 events, "
        f"{int(tier['T1'].rm)} carry commentary stating that the goal was given or celebrated and then overturned after a review, {int(tier['T2'].rm)} show review wording without a clear "
        f"statement of the initial decision, and {int(tier['T3'].rm)} lacks explicit VAR wording. The feeds do not allow us to separate a goal overturned by VAR from an on-field "
        f"disallowance later confirmed by VAR, so we cannot say that the 50 contain only the former.", BASE))
    A(P(f"The adjusted incidence-rate ratio was {f2(H['irr_adj'])} (95% CI {ci(H['irr_adj_lo'], H['irr_adj_hi'])}), compared with an unadjusted ratio of {f2(H['rate_ratio'])} "
        f"(adjusting for offside flags, shots, expected goals, venue and season; {f2(H['irr_adj_top10'])} among top-10 clubs). Across alternative event definitions, sample "
        f"restrictions, estimators and leave-one-season-out fits the adjusted ratio ranged from {f2(def_min)} to {f2(def_max)}, and Real Madrid had the highest adjusted ratio of "
        f"{len(ce)} clubs with at least 100 matches. The analyses did not detect statistically significant referee heterogeneity (p = {chi_p}) or an additional VAR-specific effect "
        f"(ratio {f2(H['var_extra_irr'])}, 95% CI {ci(H['var_extra_lo'], H['var_extra_hi'])}, p = {H['var_extra_p']:.2f}). These intervals remain compatible with materially different "
        f"effects, and unequal treatment need not appear as referee-specific concentration. Published VAR accuracy figures do not identify the error rate among Real Madrid's "
        f"disallowed goals, so we do not use them to rule errors in or out.", BASE))
    A(P(f"Limitations: all events come from public feeds rather than an official VAR log; only Real Madrid's 50 events were checked against video, and comparison clubs' incidents "
        f"have not been reviewed with the same manual protocol, so a reporting or classification difference cannot be excluded (a protocol and blank audit form are provided). "
        f"<b>The elevated recorded rate persists after adjustment, but its cause remains unresolved</b>: it could reflect tactics not captured by the covariates, reporting or "
        f"classification differences, model limitations, officiating differences, or a combination.", BASE))
    A(P("Key estimates", H2))
    kr = [["Quantity", "Value", "Note"],
          ["Real Madrid recorded events / league matches", f"{H['rm_events']} / {H['rm_matches']}", "Next club: " + f"{H['next_team']} {H['next_team_events']}"],
          ["Rate per team-match, Real Madrid vs other clubs", f"{H['rm_rate']:.3f} vs {H['others_rate']:.3f}", f"Unadjusted rate ratio {f2(H['rate_ratio'])} (95% CI {ci(H['rr_lo'], H['rr_hi'])}); exact conditional Poisson test"],
          ["Adjusted incidence-rate ratio", f"{f2(H['irr_adj'])} ({ci(H['irr_adj_lo'], H['irr_adj_hi'])})", f"Poisson GLM, SE clustered by match, n = {H['n_adj']:,} team-matches; top-10 clubs {f2(H['irr_adj_top10'])}"],
          ["Range of adjusted ratio in sensitivity analyses", f"{f2(def_min)} to {f2(def_max)}", "Sections 5.1 to 5.3"],
          ["Referee heterogeneity (15 referees)", f"p = {chi_p}", f"Power to detect log-normal rate spread SD 0.5: {100 * pow05:.0f}% (section 5.5)"],
          ["Extra Real Madrid effect at the VAR stage vs on-field stage", f"{f2(H['var_extra_irr'])} ({ci(H['var_extra_lo'], H['var_extra_hi'])})", f"p = {H['var_extra_p']:.2f}; compatible with materially different effects"]]
    A(table(kr, [6.2 * cm, 3.4 * cm, 7.8 * cm]))
    A(Spacer(1, 4))

    # ------------------------------------------------------------------ revisions
    A(P("1. Changes in interpretation relative to the draft", H1))
    A(P("The numbers below are unchanged; the wording and the inferences drawn from them are revised as follows.", BASE))
    rv = [["Draft wording", "Revised treatment"],
          ["The post's exact figures are \u201cnot reproducible\u201d; its count is lower than any reconstruction.",
           "\u201cOur reconstruction produces a different count.\u201d The post's definition and cut-off are unknown, so differences are not attributed to error. Section 2.4."],
          ["Attack volume \u201cexplains about half of the count\u201d (model fitted on other clubs predicts about 25 events).",
           f"Removed. Reported instead: adjusted IRR {f2(H['irr_adj'])} (95% CI {ci(H['irr_adj_lo'], H['irr_adj_hi'])}) versus unadjusted {f2(H['rate_ratio'])}. A forecast from other clubs does not show that attacking activity caused or explained part of the count."],
          ["\u201cNone of the signatures of targeting\u201d; the rate \u201cdoes not differ across 15 referees\u201d.",
           f"\u201cThe analyses did not detect statistically significant referee heterogeneity or an additional VAR-specific effect.\u201d VAR-stage ratio {f2(H['var_extra_irr'])} (95% CI {ci(H['var_extra_lo'], H['var_extra_hi'])}); power of the referee test is limited (section 5.5)."],
          ["\u201cVAR accuracy (96\u201398%) is far too high for errors to account for it.\u201d",
           "Removed. Overall accuracy across leagues and decision types does not identify the error rate among Real Madrid's disallowed goals. Title simulations are kept only as sensitivity analyses under assumed error probabilities."],
          ["Counting all 50 goals \u201cwould change one league title\u201d.",
           "\u201cRestoring all 50 goals while holding subsequent scoring unchanged changes the calculated champion in one season.\u201d Not part of the abstract (section 5.6)."],
          ["The residual is \u201cmost consistent with Real Madrid's attacking profile\u201d.",
           "Cause left open: unmeasured tactics, reporting differences, model limitations, officiating differences, or a combination."],
          ["\u201cNine seasons\u201d.", "\u201cEight complete seasons plus part of 2026-27\u201d (first eight rounds)."]]
    A(table(rv, [7.2 * cm, 10.2 * cm]))

    # ------------------------------------------------------------------ inclusion rules
    A(P("2. Explicit inclusion rules", H1))
    A(P("2.1 What \u201cVAR-nullified\u201d means here", H2))
    A(P("A <b>VAR-nullified goal</b> is a goal scored by a team in a La Liga league match that was ruled out, where a public feed shows evidence of a VAR review. It is a "
        "<i>recorded-event</i> definition. Two situations can produce such a record and are not equivalent: (A) a goal awarded on the pitch and then overturned after a VAR review; "
        "(B) a goal disallowed on the pitch (flag or whistle) whose disallowance was then checked and confirmed by VAR. The feeds give us no field for the initial on-field decision. "
        "We therefore classify each event by the wording of the commentary (evidence tiers, table 2) and treat the strict tier T1 as the closest approximation to situation A; "
        "sensitivity analysis D2 uses T1 only. No commentary line among the 394 events contains the words flag, whistle or linesman, but that absence does not show that situation B "
        "never occurs in the data. The manual video check of Real Madrid's 50 goals confirmed the goal and the ruling but has no field for the initial on-field decision; the audit "
        "protocol in section 6 adds it.", BASE))
    A(P("2.2 Inclusion and exclusion rules", H2))
    A(P("Table 1. Rules applied in order. D0 is the primary definition used for all headline estimates.", SMALL))
    rules = [["Rule", "Statement", "Effect"],
             ["R1 Competition and period", "League matches of La Liga (first division) from 2018-19, the first VAR season, to matches played by 12 October 2026: 3,118 completed matches (8 x 380 + 78 in 2026-27). Cup and European matches are excluded.", "3,118 matches; 6,236 team-matches"],
             ["R2 Candidate event", "Flashscore incident feed logs a \u201cGoal Disallowed\u201d for the match, with scorer, minute and reason.", "397 incidents"],
             ["R3 Team", "The event is attributed to the team that scored the ruled-out goal, not to the opponent.", "\u2013"],
             ["R4 VAR evidence (any one)", "(a) Flashscore commentary from -1 to +3 minutes around the incident carries the VAR icon or VAR, video-assistant, video-review or \u201cdisallow\u201d wording (flag <font name='DVM'>var_flag</font>); "
              "(b) the incident text mentions the video assistant referee; (c) ESPN logs a review-type event within 3 minutes (overturned goal, VAR no-goal decision, \u201cVideo Review\u201d delay or VAR decision line).", "394 events (primary definition D0); 3 incidents without evidence excluded, none Real Madrid"],
             ["R5 Goals ruled out on the pitch", "Incidents with no VAR evidence are not counted. A separate phrase-based dataset of 298 on-field disallowed goals (a floor) is used only for the VAR-stage comparison.", "Excluded from D0"],
             ["R6 Other VAR decisions", "Goals awarded by VAR, penalty and red-card reviews and checks that left the goal standing are not events, because the pipeline starts from disallowed goals.", "Not counted"],
             ["R7 Unit and duplicates", "One row per goal. Two ruled-out goals in one match count twice (largest single-match count is 3). Duplicate descriptions of the same goal are merged.", "\u2013"],
             ["R8 Reason", "Reason as logged: offside, attacking foul, handball or unspecified video review. Offside player (scorer or build-up teammate) from ESPN events within +-1 minute.", "Used in D5 to D7"],
             ["R9 Boundary case", "Second Mbapp\u00e9 goal in the 0-4 Cl\u00e1sico of 26 October 2024 (65'): ruled out by the assistant referee's flag with no VAR review in either feed. Excluded from VAR-nullified goals.", "Part of the on-field dataset"],
             ["R10 Manual validation", "All 50 Real Madrid events were checked by the study team against match video (flag <font name='DVM'>manual_validation</font>). No comparison-club event has been checked.", "Section 6"]]
    A(table(rules, [3.0 * cm, 11.4 * cm, 3.0 * cm]))
    A(P("2.3 Evidence tiers and composition of the 50 events", H2))
    A(P("Table 2. Evidence tier of recorded events, Real Madrid versus all other clubs (primary definition D0). Tiers: <b>T1</b> a verdict line (no goal, disallowed, chalked off) plus a line "
        "showing the goal was given or celebrated before the review; <b>T2</b> VAR wording but the initial decision is unclear (for example only a review-in-progress line); "
        "<b>T3</b> no explicit VAR text (kept through an ESPN event or a generic \u201cdisallow\u201d commentary line). Fisher exact p compares the Real Madrid share with the others.", SMALL))
    rows = [["Characteristic", "Real Madrid (of 50)", "Other clubs (of 344)", "Fisher p"]]
    for r in cmx.itertuples():
        rows.append([r.item, f"{int(r.rm)} ({r.rm_pct:.0f}%)", f"{int(r.others)} ({r.others_pct:.0f}%)", f"{r.fisher_p:.2f}"])
    A(table(rows, [8.2 * cm, 3.1 * cm, 3.5 * cm, 2.0 * cm]))
    A(P("The evidence mix of Real Madrid's events does not differ detectably from the others (all p above 0.10), which argues against a gross difference in the quality of the feed, but with "
        "50 events it cannot rule out a moderate one. The ESPN review-type event counts any VAR decision line near the minute, including a decision that leaves the goal standing, so it is "
        "weak corroboration of an overturn.", BASE))
    A(P("2.4 Comparison with the 10 October post", H2))
    A(P("Table 3. Counts in the post and in our reconstruction for events before 10 October 2026. Real Madrid's 50th event (an attacking foul, 71') falls on 10 October. "
        "The \u201cdifference\u201d is reconstruction minus post and is not an error rate: the post's definition, source and cut-off are not known.", SMALL))
    rows = [["Club", "Post", "Primary definition (D0)", "Offside + foul", "Offside only", "D0 minus post"]]
    for r in pv.itertuples():
        rows.append([r.team, str(r.post), str(r.primary_definition), str(r.offside_plus_foul), str(r.offside_only), f"{r.primary_definition - r.post:+d}"])
    A(table(rows, [4.2 * cm, 1.7 * cm, 3.6 * cm, 2.9 * cm, 2.5 * cm, 2.5 * cm]))
    A(P("The offside-plus-foul reading is closest to the post for Real Madrid, Atl\u00e9tico and Celta, but no single definition reproduces all seven clubs. Our reconstruction therefore "
        "produces a different count, and the direction of the post (Real Madrid first, by a wide margin) is the only feature we can compare across the two.", BASE))

    # ------------------------------------------------------------------ data
    A(P("3. Data sources and construction", H1))
    A(P("Four public, unofficial sources were queried programmatically and are not redistributed in raw form: <b>Flashscore</b> (incidents, live commentary, match statistics; "
        "primary source of events and exposure), <b>ESPN</b> public API (typed events, box scores, offside events, fouls by zone; independent corroboration), <b>Transfermarkt</b> "
        "(full referee names) and <b>Understat</b> (team-match xG and PPDA). Names were normalised by removing diacritics and token matching with a small alias table; ESPN and Flashscore "
        "matches were joined on kick-off hour and score, dropping ambiguous joins. Season coverage is complete: 380 matches in each of eight seasons plus 78 in 2026-27. Table positions "
        "are rebuilt from results because no provider supplies them. The provider terms apply, and the repository holds processed, derived tables only. The full list of tables and columns "
        "is in appendix A (also <font name='DVM'>kaggle/data_dictionary.csv</font>).", BASE))
    A(P("Outcome and exposure. The outcome is the number of recorded VAR-nullified goals for a team in a match. The adjusted model is a Poisson GLM with log link: "
        "<font name='DVM'>events ~ Real Madrid + log(1+offsides) + log(1+shots) + xG + home + season fixed effects</font>, standard errors clustered by match (dispersion 1.03). "
        "Offside flags are themselves an officiating outcome, so the estimate is conditional on them; the analysis without them is reported in section 5.2.", BASE))

    # ------------------------------------------------------------------ sensitivity
    A(P("4. Reproducible code", H1))
    A(P("Everything in this document is regenerated from the processed tables by four scripts (Python 3.12; pandas, numpy, scipy, statsmodels, matplotlib, reportlab; see "
        "<font name='DVM'>kaggle/requirements.txt</font>; no network access needed; seed 2026; about 1 minute).", BASE))
    run = ("python kaggle/reproduce.py        # sensitivity tables -> kaggle/outputs/*.csv, headline.json\n"
           "python kaggle/make_figures.py     # kaggle/outputs/figures/*.png\n"
           "python kaggle/data_dictionary.py  # checks that every column is documented -> kaggle/data_dictionary.csv\n"
           "python kaggle/build_pdf.py        # this document")
    A(Preformatted(run, CODE))
    A(Spacer(1, 4))
    A(P("The pipeline that builds <font name='DVM'>data/processed/</font> from the public feeds is unchanged (<font name='DVM'>scripts/01</font> to <font name='DVM'>11</font>; the raw caches, "
        "about 1.6 GB, are regenerated by the crawlers). Table 4 compares what <font name='DVM'>reproduce.py</font> prints with the values in the article draft.", BASE))
    chk = [["Statistic", "Article draft", "reproduce.py"],
           ["Real Madrid events / next club", "50 / 30", f"{H['rm_events']} / {H['next_team_events']}"],
           ["Rate per team-match, Real Madrid / others", "0.160 / 0.058", f"{H['rm_rate']:.3f} / {H['others_rate']:.3f}"],
           ["Unadjusted rate ratio (95% CI)", "2.76 (2.01\u20133.72)", f"{f2(H['rate_ratio'])} ({ci(H['rr_lo'], H['rr_hi'])})"],
           ["Adjusted IRR (95% CI)", "2.01 (1.45\u20132.79)", f"{f2(H['irr_adj'])} ({ci(H['irr_adj_lo'], H['irr_adj_hi'])})"],
           ["Adjusted IRR, top-10 clubs", "1.84", f2(H["irr_adj_top10"])],
           ["Extra effect at the VAR stage (95% CI)", "1.36 (0.82\u20132.23), p = 0.23", f"{f2(H['var_extra_irr'])} ({ci(H['var_extra_lo'], H['var_extra_hi'])}), p = {H['var_extra_p']:.2f}"],
           ["Referee homogeneity chi-square, 14 d.f.", "11.9, p = 0.62", f"{rh.value.iloc[0]:.1f}, p = {chi_p}"],
           ["Fixed-score scenario: champion changes", "2020-21 only", ", ".join(ts[ts.champion_changes].season)],
           ["Chance RM champion 2020-21 at assumed p = 1.7 / 5 / 10 / 25 / 50%", "1.9 / 5.1 / 9.8 / 24.7 / 49.6%", " / ".join(f"{100 * mc2021[p]:.1f}" for p in (0.017, 0.05, 0.1, 0.25, 0.5)) + "%"]]
    A(P("Table 4. Reproduction check. The Monte-Carlo values differ from the draft by simulation error only.", SMALL))
    A(table(chk, [7.2 * cm, 5.0 * cm, 5.2 * cm]))
    A(P("Core of the code (full file: <font name='DVM'>kaggle/reproduce.py</font>). Event classification and the adjusted estimator:", BASE))
    A(Preformatted(source_of(["classify_events", "fit_irr"]), CODE))

    A(PageBreak())
    A(P("5. Sensitivity analyses: overview", H1))
    A(P("The analyses below ask how far the adjusted ratio moves when (i) the event definition changes, (ii) the sample or estimator changes, (iii) the comparison is made club by club, and "
        "(iv) recording or classification is assumed to differ between clubs. They are sensitivity analyses of an observational reconstruction, not tests of a mechanism. "
        "P-values are descriptive and uncorrected for multiple comparisons.", BASE))
    A(P("5.1 Event definition and sample restrictions", H2))
    A(fig("k1_definition_sensitivity.png", 13.5 * cm))
    A(P("Figure 1. Real Madrid versus other clubs under nine event definitions (D0 to D8) and three sample restrictions (S1 to S3). Labels show Real Madrid events versus other clubs' events.", SMALL))
    rows = [["Definition / restriction", "RM", "Others", "Rate ratio (95% CI)", "Adjusted IRR (95% CI)"]]
    for r in ds.itertuples():
        rows.append([r.label, str(r.rm_events), str(r.others_events), f"{f2(r.rate_ratio)} ({ci(r.rr_lo, r.rr_hi)})", f"{f2(r.adj_irr)} ({ci(r.adj_lo, r.adj_hi)})"])
    A(table(rows, [7.0 * cm, 1.1 * cm, 1.4 * cm, 3.8 * cm, 4.1 * cm]))
    A(P(f"The adjusted ratio ranges from {f2(def_min)} to {f2(def_max)}. Restricting to ESPN-corroborated events raises it (D3 {f2(d3.adj_irr)}); restricting to 2023-24 onward, where ESPN labels "
        f"overturned goals explicitly, lowers it to {f2(s2.adj_irr)} with a wide interval ({ci(s2.adj_lo, s2.adj_hi)}; {int(s2.rm_events)} Real Madrid events). Every interval stays above 1, but "
        "the definitions overlap heavily and are not independent checks.", BASE))
    A(P("5.2 Estimator, clustering and influence of single seasons", H2))
    rows = [["Estimator for the adjusted Real Madrid IRR", "IRR", "95% CI"]] + [[r.estimator, f2(r.irr), ci(r.lo, r.hi)] for r in es.itertuples()]
    A(table(rows, [9.5 * cm, 2.5 * cm, 3.5 * cm]))
    A(P("Clustering by team is not shown: Real Madrid is a single team, so an indicator for it cannot be assessed with team clusters. Clustering by team-season widens the interval to "
        f"{ci(es.lo.iloc[1], es.hi.iloc[1])}, still above 1, although few clusters make that interval approximate. Dropping the offside control does not lower the estimate "
        f"({f2(es.irr.iloc[2])}), so the adjusted excess does not depend on controlling for an officiating outcome.", BASE))
    rows = [["Season dropped", "RM events left", "Adjusted IRR (95% CI)"]] + [[r.dropped_season, str(r.rm_events), f"{f2(r.irr)} ({ci(r.lo, r.hi)})"] for r in lo.itertuples()]
    A(table(rows, [4.0 * cm, 3.5 * cm, 6.0 * cm]))
    A(P(f"The estimate is lowest when {lo.loc[lo.irr.idxmin(), 'dropped_season']} ({int(lo.loc[lo.irr.idxmin(), 'rm_events'])} events left) is dropped ({f2(lo.irr.min())}) and highest when "
        f"{lo.loc[lo.irr.idxmax(), 'dropped_season']} is dropped ({f2(lo.irr.max())}); no single season produces the excess.", BASE))
    A(P("5.3 Comparison clubs", H2))
    A(fig("k2_club_effects.png", 12.2 * cm))
    A(P(f"Figure 2. Adjusted IRR of each club with at least 100 league matches, against all clubs other than Real Madrid (same model as the Real Madrid estimate). Real Madrid ranks "
        f"{int(rm_club['rank'])} of {len(ce)}; the next are {second.team} ({f2(second.irr)}, {ci(second.lo, second.hi)}) and {ce.iloc[2].team} ({f2(ce.iloc[2].irr)}, {ci(ce.iloc[2].lo, ce.iloc[2].hi)}). "
        "Intervals for most clubs include 1 and the list contains 24 comparisons, so rank order among the others is imprecise.", SMALL))

    A(P("5.4 Reporting and classification effects", H2))
    A(P("Reporting or classification would bias the comparison if Real Madrid's incidents were logged or labelled differently from other clubs'. One empirical check and one assumption-based "
        "analysis are available without new manual work.", BASE))
    A(P(f"<b>Evidence mix.</b> Table 2 shows the same share of explicit overturn wording (T1: {tier['T1'].rm_pct:.0f}% versus {tier['T1'].others_pct:.0f}%), a similar reason mix, and "
        f"a statistically indistinguishable share with ESPN review-type events ({cmx.rm_pct.iloc[3]:.0f}% versus {cmx.others_pct.iloc[3]:.0f}%, p = {cmx.fisher_p.iloc[3]:.2f}). This shows no sign of better recording of Real Madrid's events "
        "but is limited by 50 events and by the fact that both providers describe the same broadcasts.", BASE))
    A(P("<b>What-if analysis (assumptions, not estimates).</b> Figure 3 and table 5 rescale the adjusted IRR deterministically. If other clubs' true events were c times the recorded ones "
        "while Real Madrid's were complete, the ratio would fall to 2.01/c; if k of Real Madrid's 50 events were not true overturns it would fall to 2.01 x (50-k)/50. The factors are illustrative: "
        "we have no evidence on their size, which is why the audit in section 6 is needed.", BASE))
    A(fig("k3_ascertainment_what_if.png", 14.0 * cm))
    A(P("Figure 3. Adjusted IRR (with the 95% CI rescaled by the same factor) under assumed differential recording.", SMALL))
    rows = [["Assumption", "Adjusted IRR", "95% CI"]] + [[r.scenario, f2(r.irr), ci(r.lo, r.hi)] for r in ab.itertuples()]
    A(P("Table 5. Rescaled adjusted IRR under assumed recording differences.", SMALL))
    A(table(rows, [9.5 * cm, 3.0 * cm, 3.5 * cm]))
    A(P("The point estimate would reach 1 only if other clubs' true counts were about twice the recorded counts, or if half of Real Madrid's events were not genuine overturns, while the "
        "interval would include 1 from c above about 1.45 or from 16 non-genuine Real Madrid events. These figures show how large a differential would have to be, not that one exists.", BASE))

    A(P("5.5 Referee heterogeneity and the VAR stage", H2))
    A(P(f"Across the 15 referees with at least eight Real Madrid matches (261 matches, 45 events) the chi-square test of a common Real Madrid rate gives {rh.value.iloc[0]:.1f} on 14 d.f. "
        f"(p = {chi_p}). The analyses did not detect statistically significant referee heterogeneity, but the test has limited power: if true referee rates varied log-normally with a standard "
        f"deviation of 0.5 it would reject in about {100 * rh.value.iloc[2]:.0f}% of simulated datasets, and with SD 0.25 in {100 * rh.value.iloc[1]:.0f}%. Referee-specific concentration is also "
        f"not a necessary feature of unequal treatment. Using the same model on stacked VAR-stage and on-field counts, the extra Real Madrid effect at the VAR stage was {f2(H['var_extra_irr'])} "
        f"(95% CI {ci(H['var_extra_lo'], H['var_extra_hi'])}); the on-field-only adjusted ratio was {f2(H['onfield_irr_adj'])}. An interval running from a modest deficit to more than a doubling "
        "does not support a conclusion of no VAR-specific effect. The on-field dataset is phrase-based, so a floor.", BASE))

    A(P("5.6 Title calculation as a fixed-score scenario", H2))
    A(P("Restoring all 50 goals while holding subsequent scoring unchanged changes the calculated champion in one season. The table recomputes each season from all 380 results with La Liga's "
        "tie-break order; it describes arithmetic on final scores, not how the matches would have unfolded, and treats every ruling as wrong.", BASE))
    rows = [["Season", "RM events", "Champion (actual)", "RM pts / best other (actual)", "RM pts / best other (restored)", "Calculated champion changes"]]
    for r in ts.itertuples():
        rows.append([r.season, str(r.rm_events), r.champion_actual, f"{r.rm_pts_actual} / {r.best_other_pts_actual}", f"{r.rm_pts_if_all_restored} / {r.best_other_pts_if_all_restored}", "Yes" if r.champion_changes else "No"])
    A(KeepTogether([P("Table 6. Fixed-score scenario: every Real Madrid goal restored, all other scoring unchanged.", SMALL),
                    table(rows, [2.0 * cm, 1.8 * cm, 4.0 * cm, 3.4 * cm, 3.6 * cm, 2.6 * cm])]))
    A(P(f"In 2020-21 Real Madrid ({int(t2021.rm_pts_actual)} points) would level with Atl\u00e9tico ({int(t2021.best_other_pts_if_all_restored)}) at {int(t2021.rm_pts_if_all_restored)} and lead on head-to-head. "
        "Because the true error probability is not known for these decisions, the table below varies an <b>assumed</b> probability that each ruling was wrong (20,000 simulations per cell); "
        "1.7% is the complement of a multi-league accuracy figure used only as an illustrative low value, and none of the values is a validated estimate for this dataset. "
        "Seasons not shown have zero probability at every value.", BASE))
    rows = [["Season", "p = 1.7%", "p = 5%", "p = 10%", "p = 25%", "p = 50%"]]
    for s, g in mc.groupby("season"):
        if g.p_rm_champion.max() > 0:
            rows.append([s] + [f"{100 * v:.1f}%" for v in g.sort_values("assumed_error_probability").p_rm_champion])
    A(P("Table 7. Chance that Real Madrid would be champion in a season it did not win, under assumed independent error probabilities.", SMALL))
    A(table(rows, [3.0 * cm, 2.4 * cm, 2.4 * cm, 2.4 * cm, 2.4 * cm, 2.4 * cm]))

    # ------------------------------------------------------------------ audit protocol
    A(P("6. Manual audit protocol for comparison clubs", H1))
    A(P("<b>Status: not yet performed.</b> Only Real Madrid's 50 events were reviewed against video. Reviewing the comparison clubs' incidents with the same protocol would test directly whether "
        "part of the difference is a reporting or classification effect, which no analysis of the feeds alone can do. The key and a blank reviewer form are provided "
        "(<font name='DVM'>manual_audit_key.csv</font>, <font name='DVM'>manual_audit_form.csv</font>).", BASE))
    pr = [["Step", "Specification"],
          ["Scope", "All 394 primary-definition events in randomised order (A001 to A394). Priority 1 (181 events): Real Madrid (50) and the five clubs with most events (Villarreal 30, FC Barcelona 27, Atl\u00e9tico de Madrid 26, Sevilla 25, Celta de Vigo 23; 131). Priority 2: the rest."],
          ["Blinding", "An independent person cuts the clips and keeps the key. Reviewers receive the form (audit id, date, minute) with no club or player names where the footage allows, and are not told the hypothesis."],
          ["Fields", "initial_onfield_decision (goal given / flag raised before goal / whistle before goal / unclear); var_action (check only / review overturn / review confirmed on-field decision / other); final_decision; final_reason; event_meets_protocol; video source."],
          ["Event meets protocol", "The ball is seen to enter the goal and the goal is given or flagged by the on-field officials; the final decision is no goal; VAR involvement is visible (review signal, monitor, on-screen graphic or official statement). Subtype A (given then overturned), B (disallowed on field then checked by VAR) or C (other)."],
          ["Reviewers", "Two independent reviewers per priority-1 event, a third to resolve disagreements. Cohen's kappa is reported for event_meets_protocol and for the subtype."],
          ["Completeness check", "Optional second stage: watch a random sample of matches without a logged event (40 per priority-1 club) to count disallowed goals that the feeds missed, to test for under-recording by club."],
          ["Pre-specified analysis", "(1) Share of events meeting protocol by group with risk difference and 95% CI; (2) re-estimate the adjusted IRR from audited events only (all subtypes, then subtype A only); (3) report whether the lower bound stays above 1; (4) publish the filled forms, kappa and any deviations."]]
    A(P("Table 8. Planned audit.", SMALL))
    A(table(pr, [3.4 * cm, 14.0 * cm]))
    rows = [["Share valid, group 1", "Share valid, group 2", "Real Madrid n", "Comparison n", "Power (two-sided 5%)"]] + [
        [f"{r.valid_share_group_1:.2f}", f"{r.valid_share_group_2:.2f}", str(r.n_rm), str(r.n_comparison), f"{100 * r.power:.0f}%"] for r in pw.itertuples()]
    A(P("Table 9. Power of the priority-1 audit to detect a lower share of valid events in one group (normal approximation). A difference of 15 points is detected about half the time; 20 points about 80%.", SMALL))
    A(table(rows, [3.5 * cm, 3.5 * cm, 3.0 * cm, 3.0 * cm, 4.0 * cm]))

    # ------------------------------------------------------------------ limitations
    A(P("7. Limitations and conclusion", H1))
    lim = ["Events come from public feeds, not an official VAR log; the on-field referee is recorded, not the VAR official. Early seasons are less well corroborated by ESPN.",
           "The initial on-field decision is not recorded, so situations A and B cannot be separated (section 2.1). The classifier uses commentary wording and is not validated against video.",
           "Comparison clubs' incidents have not been reviewed manually (section 6). The what-if analysis is arithmetic on assumed factors.",
           "Offside flags are an officiating outcome. Adjusted estimates are conditional on them; the estimate without them is not lower.",
           "50 events over eight complete seasons plus part of 2026-27, with 11 in 2022-23. Tests are descriptive and uncorrected for multiplicity; intervals for team-season clustering are approximate.",
           "\u201cTop-10\u201d is defined by the final table, a partly post-outcome variable. xG and PPDA are modelled or proxy measures; protocol, technology and coaching changes are absorbed only by season effects.",
           "Fixed-score scenarios ignore tactical and psychological knock-on effects, and the assumed error probabilities are not validated for these decisions."]
    for t in lim:
        A(P("\u2022 " + t, ParagraphStyle("li", parent=BASE, leftIndent=10, firstLineIndent=-8, spaceAfter=2)))
    A(P("<b>Conclusion.</b> The recorded rate of VAR-nullified goals is higher for Real Madrid than for other clubs, and it remains higher after adjusting for offside flags, shots, expected goals, venue and "
        f"season (adjusted IRR {f2(H['irr_adj'])}, 95% CI {ci(H['irr_adj_lo'], H['irr_adj_hi'])}; unadjusted {f2(H['rate_ratio'])}). The estimate is stable across the definitions, estimators and samples "
        "examined here. The analyses did not detect statistically significant referee heterogeneity or an additional VAR-specific effect, but their intervals are wide. <b>The cause of the elevated "
        "recorded rate remains unresolved.</b> Event-level tracking data, an official VAR log and the manual audit of comparison clubs would address that.", BOX))
    A(P("Reference for context only: Spitz J, Wagemans J, Memmert D, Williams AM, Helsen WF. Video assistant referees (VAR): the impact of technology on decision making in association football referees. "
        "J Sports Sci 2021;39(2):147-153. doi:10.1080/02640414.2020.1809163. Its accuracy figures cover other competitions and decision types and are not used for inference here.", SMALL))

    # ------------------------------------------------------------------ appendix: dictionary
    A(PageBreak())
    A(P("Appendix A. Data dictionary", H1))
    A(P("Types: string, integer, float, boolean, date/time. Blank values are missing. Club names are normalised across providers. The file <font name='DVM'>kaggle/data_dictionary.csv</font> "
        "holds the same content and is checked against the actual column headers by <font name='DVM'>data_dictionary.py</font>.", BASE))
    import data_dictionary as DD
    for path, (desc, cols) in DD.TABLES.items():
        sub = dd[dd.table == path]
        blk = [P(f"<font name='DVM'>{esc(path)}</font>", H2), P(esc(desc) + f" ({len(sub)} columns)", SMALL)]
        rows = [["Column", "Type", "Description"]] + [[f"<font name='DVM' size='6.6'>{esc(r.column)}</font>", r.type, esc(r.description)] for r in sub.itertuples()]
        t = table(rows, [4.3 * cm, 1.7 * cm, 11.4 * cm])
        A(KeepTogether(blk + [Spacer(1, 2)]))
        A(t)
    doc = SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.8 * cm,
                            title="Real Madrid and recorded VAR-nullified goals in La Liga, 2018-19 to October 2026: Kaggle companion",
                            subject="Revised abstract, inclusion rules, data dictionary, reproducible code and sensitivity analyses",
                            keywords="La Liga, VAR, Real Madrid, Poisson regression, sensitivity analysis", author="")
    doc.build(st, onFirstPage=footer, onLaterPages=footer)
    print("wrote", PDF)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(HERE))
    main()
