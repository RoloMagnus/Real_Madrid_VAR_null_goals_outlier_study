# Real Madrid and VAR-nullified goals: an outlier case study (La Liga 2018-19 to 12-Oct-2026)

A fan claim says VAR (or referees) work against Real Madrid because it leads La Liga in goals ruled out by VAR. This project validates the claim and tests it.

## Main findings
- **The outlier is real.** Real Madrid has 50 VAR-nullified goals vs 30 for Villarreal (2.8x the rate of other teams). The exact numbers in the original post (42 for Real Madrid) could not be reproduced; the direction and ranking hold in two independent sources.
- **Attack volume explains about half.** After controlling for offsides, shots, xG, pressing (PPDA), fouls and cards, Real Madrid is still about 2x other teams.
- **No evidence of VAR or referee targeting.** In Real Madrid matches the split of nullified goals follows each side's share of offsides and goal opportunities; opponents are not significantly spared; the rate is similar across referees; the excess also exists for goals ruled out on the pitch with no VAR; VAR accuracy (96-98%) is too high for errors to explain it.
- **Titles.** Counting every Real Madrid nullified goal as wrong changes one title (2020-21, level on points and ahead on head-to-head). 44 matches contain a nullified goal, 15 ended in a draw or loss, 13 would have changed result (21 points over 8.2 seasons).

## Contents
| Path | What it is |
|---|---|
| `Real Madrid VAR Nullified Goals - Analysis.xlsx` | Final report: validation of the post, the 50-goal breakdown (with manual validation flag and video links), statistical framework, EDA, title scenarios, on-field disallowed goals (13 sheets) |
| `Real Madrid VAR - EDA.ipynb` | EDA notebook with all graphs (player concentration, matches affected, champion vs not, title scenarios, more) |
| `RM_nullified_goals_breakdown_validated.xlsx` | Manually validated breakdown (source of the validation flag and links) |
| `scripts/` | Pipeline: 01 crawl ESPN, 02 crawl Flashscore, 03 build dataset, 04 Understat xG/PPDA, 06 referees (Transfermarkt), 05 enrich, 09 fouls by zone, 10-11 goals ruled out on the pitch, 07 statistics, 08 build Excel |
| `data/processed/` | Cleaned tables and `analysis.pkl` (inputs of the notebook and Excel builder) |
| `data/raw/` | Small raw tables (match lists, Understat); the large crawler caches are not in the repo |
| `figures/` | PNG charts exported by the notebook |

## Reproducing
- **Notebook and Excel only** (no network needed): run `Real Madrid VAR - EDA.ipynb`, then `python scripts/08_build_excel.py`.
- **From scratch**: run the scripts in the order above (needs internet; the crawlers rebuild `data/raw/*_cache`, about 1.6 GB, then 07 and 08).
- Python 3.12 with pandas, numpy, scipy, statsmodels, matplotlib, seaborn, xlsxwriter, openpyxl, requests, nbconvert/ipykernel.

## Data sources
Flashscore (incidents, commentary, match stats), ESPN public API (match logs, VAR events, offsides), Transfermarkt (referee names), Understat (xG, PPDA). VAR accuracy references: Spitz et al. 2021 (J Sports Sci), Premier League and FIFA figures (see sheet 10 of the workbook for verification status).

## Limitations
Goal events are reconstructed from public feeds, not an official VAR log. The on-field referee is not the VAR official. The residual 2x after controls is a hypothesis (attacking profile) that would need offside-line tracking data to confirm. 2026-27 is a partial season (8 rounds).
