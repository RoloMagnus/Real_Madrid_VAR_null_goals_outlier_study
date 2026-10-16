# Pipeline audit (15 October 2026)

**Trigger.** A reader comment on the Medium post argued that four manually checked rows (a wrong minute, a non-existent VAR review, a merged match) are "a good reminder that a clean pipeline can still carry bad state all the way through". This audit tests whether the pipeline itself carries errors of those three types.

**Status.** Findings are documented here. As agreed, **no published number was changed**: the fixes below were tested only in an isolated copy and are *not* applied to the scripts, data, Excel report, notebook or article figures.

## 1. Short answer

1. **The four rows were errors of the hand-built validation sample, not of the pipeline.** For all four the pipeline already held the correct record (see section 3.4). The article's wording (Section 4.4) was ambiguous about this and has been clarified.
2. **The commenter's general point is fair, and the audit found five small defects of exactly that kind** in the full pipeline (section 4). None changes Real Madrid's count (50). The largest change in any headline estimate is **0.05** on a rate ratio of about 2.0.
3. **No wrong minutes, no mismatched matches in the main pipeline, no double counting.** One league-wide event (Getafe, 2020, not Real Madrid) is counted as a VAR nullification on weaker evidence than the rule used elsewhere.

## 2. What was tested

| # | Check | Result |
|---|---|---|
| 1 | **Minute**: Flashscore incident minute vs ESPN's explicit VAR minute (286 events) | identical 47%; within 1 minute 79%; within 2 minutes 95.5%; all found within a +/-3 minute window. Flashscore is earlier in 136 of 286 because ESPN logs the VAR *decision*, Flashscore the *goal* |
| 2 | **VAR evidence**: independent re-derivation for all 397 candidate incidents | 286 have ESPN explicit VAR event + Flashscore VAR wording; 105 Flashscore VAR wording only; 2 ESPN video-review delay only; 4 no VAR reference at all |
| 3 | Does the VAR commentary in the window concern the goal (not a penalty or card)? | 389 of 389 events with VAR lines (also under a stricter pattern); 0 failures |
| 4 | Double counting (same team, same match, within 2 minutes) | 0 |
| 5 | **Recall** vs ESPN's own "GOAL OVERTURNED BY VAR" log, 2022-23 onwards | 122 of 128 present; none of the 6 missing involves Real Madrid (some may be stoppage-time minute mismatches; not reviewed individually) |
| 6 | **ESPN <-> Flashscore merge** (kick-off hour + score), team names verified | 3,034 single-candidate matches, **0 mis-merges**; 78 ambiguous matches left blank by design (18 events, none Real Madrid); 6 with no candidate |
| 7 | **Understat merge**: Flashscore goals vs Understat goals scored/conceded | 6,120 joined, **0 disagreements**; 116 team-matches not joined (Huesca 76, Oviedo 38, abandoned match 2) |
| 8 | **Referee merge**: Transfermarkt full name vs Flashscore short name | 616 of 617 surnames agree; 1 disagreement (Malaga-Villarreal, 17 Sep 2026, not a Real Madrid match) |
| 9 | **Foul-zone merge** (`09_fouls_espn.py`) | **1 confirmed mis-merge** and 7 matches without data (section 4, defect 3) |
| 10 | Pipeline output for the four hand-built sample rows | correct for all four (section 3.4) |
| 11 | Manual validation file: rows, matches and video links | 50 rows, 44 matches, 44 distinct links; one link per match, none shared across matches |

## 3. The three claims, one by one

### 3.1 "Wrong minute"
Not found in the pipeline. The minute is Flashscore's displayed minute of the incident (1-indexed: a goal at clock 53:43 is the 54th minute). ESPN's tag is stamped when the VAR decision is taken, 0-3 minutes later, and some hand-recorded sources use the 0-indexed clock (53). Differences of +/-1 versus other sources are therefore a convention, not an error. The half is derived from the base minute (45+x is first half). The user's own hand-built sample had one genuinely wrong minute (Real Madrid-Levante, 43' instead of 18').

### 3.2 "Non-existent VAR review"
Mostly not found, with one real inconsistency. Flashscore's *Goal Disallowed* incident is a candidate, not proof of VAR. The pipeline accepts an event as VAR-confirmed on VAR wording in the commentary within -1/+3 minutes, or an ESPN VAR event, or an ESPN "Video Review" delay. Re-deriving the evidence independently:

* **391 of 394** counted events have explicit VAR wording and/or an explicit ESPN VAR event.
* **2 counted events rest on an ESPN video-review delay only:** Valencia-Girona 3 Nov 2018 (reason code "video review", no player) and **Real Madrid-Levante 20 Oct 2018 (Asensio, 18')**, where Flashscore says only "has a goal ruled out for offside". The Asensio goal was validated against video by the study team.
* **1 counted event has no VAR reference at all:** Getafe (Mata), Levante-Getafe, 19 Jul 2020: "GOAL DISALLOWED! ... has a goal ruled out, incredibly, for offside". It was admitted because the matching rule accepts the bare word *disallow*, which is also used for on-field decisions. Three events with the same kind of evidence were excluded (Mandi 2020, Budimir 2026, Stuani 2025), so the rule was applied inconsistently. Not a Real Madrid event.
* **Sensitivity (strictest rule, explicit VAR wording only):** 391 events, Real Madrid 49, rate ratio **2.72** (95% CI 1.97-3.68) vs 2.76 in the main analysis.

### 3.3 "Merged match"
Not found in the main pipeline (checks 6-8). Found in a secondary covariate (section 4, defect 3). The ESPN join used for corroboration and offside-player attribution is keyed on kick-off hour + score and never uses team names; the audit verified the team names afterwards and found no disagreement among 3,034 matches. Ambiguous matches are dropped (left blank), never guessed.

### 3.4 The four rows of the hand-built sample

| Sample row | Hand-built value | Pipeline output |
|---|---|---|
| 26 Sep 2018 Sevilla, Modric | minute 53 | 54' (53:43 on the clock; same event, 1-indexed minute) |
| 20 Oct 2018 Levante, Asensio | minute 43 | **18'** (correct) |
| 1 Dec 2018 Valencia, Benzema | offside nullified goal | **no incident at all** (correct; no VAR review in either feed) |
| 10 Mar 2019 Valladolid, Modric/Varane | Modric offside, Varane passive | Valladolid match holds only Valladolid's own goal (Guardiola 14'); the Modric offside is the **16 Mar 2019 Celta match, 56'** (correct) |

## 4. Defects found

| # | Defect | Where | Effect | Status |
|---|---|---|---|---|
| 1 | Bare word *disallow* accepted as VAR evidence | `scripts/03_build_dataset.py` (VAR-text regex) | 1 non-VAR event counted (Getafe): 394 instead of 393; Real Madrid unchanged | documented, not applied |
| 2 | Two events counted on a video-review delay only | evidence rule (`07_analysis.py` `var_confirmed`) | includes Real Madrid-Levante 2018 (video-validated); strict-rule sensitivity above | kept, sensitivity reported |
| 3 | Substring name fallback maps ESPN "Deportivo" (La Coruna) to Deportivo Alaves | `scripts/09_fouls_espn.py`; same fallback in the ESPN check of `07_analysis.py` | Alaves-Valencia (15 Sep 2026) received foul data from La Coruna-Valencia; 7 La Coruna matches have no foul-zone data. The earlier note "ESPN lists the match twice" was a **wrong diagnosis** of this | documented, not applied |
| 4 | Understat aliases missing: "Huesca" vs "SD Huesca", "Oviedo" vs "Real Oviedo" | `scripts/05_enrich.py` | xG missing for 76 team-matches (Huesca), PPDA for 114 (+ the opponents' terms): 230 team-matches leave the PPDA models. This is the "1.2% / 1.9% missing" reported in the article, whose cause was not diagnosed | documented, not applied |
| 5 | Abandoned match counted as a 0-0 draw | Flashscore lists Rayo Vallecano-Athletic (10 Oct 2026) as 0-0; ESPN status "Abandoned" | 2 team-matches; no nullified goal; slightly affects the partial 2026-27 table | assumption, documented |

### Impact of fixing 1, 3 and 4 (tested in an isolated copy; repository unchanged)

| Estimate | Published | With fixes |
|---|---|---|
| VAR-confirmed events / Real Madrid | 394 / 50 | 393 / 50 |
| Rate ratio per match, all teams (top-10) | 2.76 (2.37) | 2.77 (2.38) |
| Volume model IRR, all teams (n) | 2.01 (6,160) | 2.04 (6,236) |
| Volume model IRR, top-10 | 1.84 | 1.85 |
| + PPDA, all teams (n) | 1.99 (6,006) | 1.94 (6,234) |
| + fouls/cards/PPDA, all teams (n) | 2.02 (5,980) | 1.97 (6,224) |
| Leave-RM-out forecast (95% interval) | 25.0 (16-35) | 24.6 (15-35) |
| Within-match symmetry p (offsides / goal opportunities) | 0.110 / 0.135 | 0.110 / 0.130 |
| Opponents spared, obs/exp (p) | 0.70 (0.112) | 0.70 (0.114) |
| Referee heterogeneity p | 0.617 | 0.617 |
| Extra Real Madrid effect at the VAR stage (p) | 1.36 (0.23) | 1.35 (0.24) |
| Net points ledger, Real Madrid | -9 | -9 |
| xG / PPDA missing | 1.22% / 1.86% | 0.00% / 0.03% |

No conclusion changes.

## 5. Assumptions made in the pipeline (explicit list)

1. **Minute** = Flashscore's displayed minute of the goal incident (1-indexed); **half** from the base minute.
2. **VAR-confirmed** requires VAR wording or an ESPN VAR/review event near the incident; *Goal Disallowed* alone is a candidate. Weak-evidence cases are listed above.
3. **Scorer** is the player whose goal was ruled out; "passive player" comes from ESPN offside events and is blank when ESPN does not name one.
4. **Joins:** Flashscore id is the primary key; ESPN by kick-off hour + score (ambiguous dropped); Understat by team + date (+/-2 days); Transfermarkt by season + team names; foul zones by season + home + away.
5. **Complete-case modelling:** rows with missing covariates are dropped; sample sizes are reported with each model.
6. **Referee** = on-field referee (VAR-room official unavailable).
7. **League table** is rebuilt from results; abandoned matches are counted as played with the feed's score.
8. **On-field disallowed goals** are mined from commentary phrasing and are a floor.
9. **Manual validation:** the validated workbook starts from the pipeline's breakdown (same columns), so its agreement on date/player/minute shows those fields were not changed, not independent verification. The independent part is the manual video check (flag and link per goal), which this audit did **not** re-verify (the videos were not opened).
10. **Source independence is not guaranteed.** Flashscore and ESPN are unofficial public feeds and may share an upstream data provider; their agreement is weaker evidence than independent provenance. No official VAR log is available.

## 6. Reproducing the audit

```
python scripts/audit/01_evidence_and_minutes.py        # evidence tiers, minute agreement  (writes data/processed/audit_event_evidence.csv)
python scripts/audit/02_joins.py                       # ESPN, foul-zone, Understat, referee joins
python scripts/audit/03_weak_evidence_recall_duplicates.py
python scripts/audit/04_unjoined_rows_and_text_test.py
python scripts/audit/05_sample_rows_and_sensitivity.py
python scripts/audit/06_apply_fixes_in_isolated_copy.py   # needs the isolated copy described in its docstring
python scripts/audit/07_compare_before_after.py
```
Scripts 01-05 need the raw caches in `data/raw/` (regenerated by the crawlers) and take a few minutes. Scripts 06-07 reproduce the before/after table.
