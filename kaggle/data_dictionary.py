"""Data dictionary for the tables in data/processed/ and kaggle/outputs/.

    python kaggle/data_dictionary.py     # checks every column is documented, writes kaggle/data_dictionary.csv
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent

S, I, F, B, D = "string", "integer", "float", "boolean", "date/time"

TABLES = {
    "data/processed/disallowed_goals_enriched.csv": ("One row per Flashscore 'Goal Disallowed' incident (397), all clubs, with context.", {
        "season": (S, "Season label, e.g. 2018-19 (August to July; the COVID-delayed 2019-20 finish is mapped explicitly)."),
        "fs_id": (S, "Flashscore match identifier; primary key of the match."),
        "date": (D, "Local match date (Europe/Madrid)."),
        "kickoff": (D, "Local kick-off time (Europe/Madrid)."),
        "home": (S, "Home club (normalised name)."),
        "away": (S, "Away club (normalised name)."),
        "final": (S, "Final score as home-away."),
        "team": (S, "Club whose goal was ruled out."),
        "opponent": (S, "Opponent of `team` in the match."),
        "venue": (S, "Home or Away, from the perspective of `team`."),
        "player_short": (S, "Scorer as abbreviated by Flashscore (e.g. 'Mbappe K.')."),
        "player": (S, "Scorer slug from the Flashscore URL (e.g. 'mbappe-kylian')."),
        "minute": (S, "Minute of the incident as displayed (e.g. 45'+2')."),
        "minute_num": (I, "Minute as a number; stoppage time is added to the base minute (90+7 = 97)."),
        "half": (I, "1 or 2, from the base minute; stoppage time inherits the half."),
        "reason_fs": (S, "Reason logged by Flashscore: offside, Foul (attacking foul), handball or video review (unspecified)."),
        "score_home": (I, "Running home score before the incident (Flashscore incident feed)."),
        "score_away": (I, "Running away score before the incident."),
        "fs_text": (S, "Free text attached to the Flashscore incident, when present (about 78% of rows)."),
        "var_commentary": (S, "Flashscore live-commentary lines from -1 to +3 minutes around the incident that carry the VAR icon, VAR or "
                              "video wording or the word 'disallow', joined with ' || '. Mostly written as commentary, not an official log."),
        "var_flag": (B, "True if any such commentary line exists or the incident text mentions the video assistant referee. Looser than "
                        "'explicit VAR wording': it also fires on a generic 'disallow' line (1 Getafe incident in the 394)."),
        "ref_short": (S, "Referee name as abbreviated by Flashscore (on-field referee, not the VAR official)."),
        "pos_before": (F, "League position of `team` at kick-off, rebuilt from results (points, goal difference, goals); blank in round 1."),
        "pts_before": (I, "Points of `team` before the match."),
        "played_before": (I, "Matches played by `team` before the match."),
        "opp_pos_before": (F, "League position of the opponent at kick-off."),
        "team_final_pos": (I, "Final league position of `team` in the season (partial table for 2026-27)."),
        "opp_final_pos": (I, "Final league position of the opponent."),
        "referee_full": (S, "Full referee name from Transfermarkt match sheet (or majority-vote mapping of the Flashscore name)."),
        "referee_source": (S, "Where `referee_full` came from."),
        "player_full": (S, "Scorer's full accented name, mapped from the Flashscore slug to ESPN roster names."),
        "context_text": (S, "Decision sentence extracted from `var_commentary` (or `fs_text`) used for the 'var_decision_text' field of the report."),
        "offside_player_espn": (S, "ESPN offside event text for the same team within +-1 minute (who was flagged), if any."),
        "category": (S, "Derived class: offside by goalscorer, offside by teammate in build-up, offside player not identified, foul, handball, other."),
        "half_label": (S, "1st half or 2nd half."),
        "goal_effect": (S, "What the goal would have meant given the score before it: Go-ahead / opener, Extend lead, Equaliser, Reduce deficit."),
        "team_gf": (I, "Final goals scored by `team` in the match (actual result)."),
        "team_ga": (I, "Final goals conceded by `team`."),
        "pts_actual": (I, "Points `team` earned in the match."),
        "pts_if_allowed": (I, "Points if `team` had scored one more goal and nothing else changed (fixed-score what-if)."),
        "points_lost": (I, "pts_if_allowed minus pts_actual for this incident alone."),
        "result_changed": (B, "True if the fixed-score what-if changes the match result (points_lost > 0)."),
        "espn_corroborated": (B, "True if an ESPN review-type event (overturned goal, VAR no-goal decision, or any 'Video Review' / VAR decision line, "
                                 "including 'decision on field stands/cancelled') lies within 3 minutes; blank if no ESPN match record. It does not "
                                 "by itself show that a goal was overturned."),
    }),
    "data/processed/team_match.csv": ("One row per team per league match (6,236 = 3,118 x 2): exposure covariates.", {
        "season": (S, "Season label."), "fs_id": (S, "Flashscore match id."), "kickoff": (D, "Local kick-off."),
        "team": (S, "Club of this row."), "opponent": (S, "Opponent."), "venue": (S, "H or A."),
        "gf": (I, "Goals scored by `team`."), "ga": (I, "Goals conceded."),
        "possession": (F, "Possession %, Flashscore."), "shots": (F, "Total shots, Flashscore."), "sot": (F, "Shots on target."),
        "corners": (F, "Corners."), "yellow": (F, "Yellow cards."), "shots_off": (F, "Shots off target."), "blocked": (F, "Blocked shots."),
        "offsides": (F, "Offside flags against `team` (an officiating outcome; see threats to validity)."),
        "fouls": (F, "Fouls committed."), "red": (F, "Red cards (not listed when zero; set to 0)."),
        "xg_fs": (F, "Flashscore xG; exists from 2022-23 only (55% blank). Used only as a cross-check."),
        "big_chances": (F, "Flashscore big chances (77% blank)."), "shots_in_box": (F, "Shots inside the box (77% blank)."),
        "box_touches": (F, "Touches in the opposition box (77% blank)."),
        "pos_before": (I, "League position before kick-off."), "pts_before": (I, "Points before the match."),
        "played_before": (I, "Matches played before."), "date": (D, "Local match date."),
        "xg": (F, "Understat expected goals of `team` (1.2% missing); used in the models."),
        "xga": (F, "Understat expected goals against."),
        "ppda_att": (F, "Passes allowed by `team`'s opponent in the pressing zone (PPDA numerator component, Understat)."),
        "ppda_def": (F, "Defensive actions by `team` in the pressing zone (PPDA denominator component)."),
        "opp_ppda_att": (F, "Same as ppda_att for the opponent."), "opp_ppda_def": (F, "Same as ppda_def for the opponent."),
        "ppda": (F, "Passes allowed per defensive action of `team`."), "opp_ppda": (F, "PPDA of the opponent in the same match."),
        "final_pos": (I, "Final league position of `team` that season."),
        "top10": (B, "True if `team` finished in the top 10 of that season's final table (post-outcome definition)."),
        "pts": (I, "Points earned in the match."),
    }),
    "data/processed/RM_nullified_goals_breakdown.csv": ("The 50 Real Madrid goals in the primary definition (28 report fields + manual flag + link).", {
        "rank": (I, "Chronological order 1-50."), "date": (D, "Match date."), "season": (S, "Season (e.g. 2018-2019)."),
        "round": (F, "League round."), "team (goal nullified)": (S, "Always Real Madrid."), "rival": (S, "Opponent."),
        "active_player": (S, "Scorer."), "passive_player": (S, "Offside teammate in the build-up (ESPN event), when applicable."),
        "local_flag": (B, "True if Real Madrid played at home."), "var_reason": (S, "Offside, Foul, Handball or Video review (unspecified)."),
        "context_category": (S, "Derived class (see disallowed_goals_enriched.category)."), "minute": (I, "Minute (stoppage added)."),
        "minute_display": (S, "Minute as displayed."), "half": (S, "first or second."),
        "score_before_goal (team-opp)": (S, "Score before the goal, Real Madrid first."),
        "what_the_goal_would_have_been": (S, "Go-ahead / opener, Extend lead, Equaliser or Reduce deficit."),
        "team_goals_final": (I, "Real Madrid final goals."), "rival_goals_final": (I, "Opponent final goals."),
        "outcome": (S, "WIN, DRAW or LOSS from Real Madrid's perspective."),
        "points_lost_due_to_nullification": (I, "Fixed-score what-if points for this goal alone."),
        "league_position_at_time": (F, "Real Madrid position at kick-off."), "rival_position_at_time": (F, "Opponent position at kick-off."),
        "points_at_time": (I, "Real Madrid points before the match."), "referee_on_field": (S, "On-field referee."),
        "laliga_title_won_flag": (B, "True if Real Madrid won the title that season."), "la_liga_champion": (S, "Champion of the season."),
        "var_decision_text": (S, "Decision sentence from commentary (blank for 1 event)."),
        "var_evidence": (S, "Label of the evidence class in the report; 'Explicit VAR wording / ESPN review' for all 50 (it does not separate "
                            "T1/T2/T3; see events_with_evidence_tier)."),
        "manual_validation": (B, "True if the study team checked the goal against match video (all 50)."),
        "links": (S, "Video link used in the manual check."),
    }),
    "data/processed/onfield_disallowed_events.csv": ("Goals ruled out on the pitch without VAR wording (298; a floor, phrase-based).", {
        "rank": (I, "Chronological order."), "fs_id": (S, "Flashscore match id."), "date": (D, "Match date."), "season": (S, "Season."),
        "round": (I, "League round."), "team": (S, "Club whose goal was ruled out."), "rival": (S, "Opponent."),
        "local_flag": (B, "True if `team` was at home."), "active_player": (S, "Scorer."),
        "reason": (S, "Offside, Foul, Handball or Other."),
        "kind": (S, "Commentary pattern that produced the row: flag, goal_disallowed_line, ruled_out, whistle_foul, thought_scored."),
        "minute": (I, "Minute (stoppage added)."), "minute_display": (S, "Minute as displayed."), "half": (S, "first or second."),
        "score_before_goal": (S, "Score before the goal, `team` first."), "goal_would_have_been": (S, "Effect of the goal on the score."),
        "team_goals_final": (I, "Final goals of `team`."), "rival_goals_final": (I, "Final goals of the opponent."),
        "outcome": (S, "WIN, DRAW or LOSS."), "points_lost": (I, "Fixed-score what-if points."),
        "league_position_at_time": (F, "Position at kick-off."), "rival_position_at_time": (F, "Opponent position at kick-off."),
        "points_at_time": (I, "Points before the match."), "referee_on_field": (S, "Referee."), "commentary": (S, "Source commentary line."),
        "season_final_pos": (I, "Final position of `team` in the season."),
    }),
    "data/processed/matches.csv": ("One row per league match (3,118): results and referee (Flashscore).", {
        "season": (S, "Season."), "fs_id": (S, "Flashscore match id."), "date_utc": (D, "UTC kick-off."), "round": (S, "Round label."),
        "home": (S, "Home club."), "away": (S, "Away club."), "home_goals": (I, "Final home goals."), "away_goals": (I, "Final away goals."),
        "kickoff_local": (D, "Local kick-off."), "date": (D, "Local date."), "referee_short": (S, "Abbreviated on-field referee."),
    }),
    "data/processed/final_tables.csv": ("Final league table per season rebuilt from results (180 rows).", {
        "team": (S, "Club."), "pts": (I, "Points."), "gd": (I, "Goal difference."), "gf": (I, "Goals for."), "played": (I, "Matches played."),
        "final_pos": (I, "Final position (points, goal difference, goals)."), "season": (S, "Season."), "relegated": (B, "True if relegated."),
    }),
    "kaggle/outputs/events_with_evidence_tier.csv": ("The 394 primary-definition events with the evidence tier added by reproduce.py.", {
        "season": (S, "Season."), "fs_id": (S, "Flashscore match id."), "date": (D, "Match date."), "team": (S, "Club whose goal was ruled out."),
        "opponent": (S, "Opponent."), "venue": (S, "Home or Away."), "player_full": (S, "Scorer."), "minute_num": (I, "Minute."),
        "reason_fs": (S, "Reason logged by Flashscore."),
        "tier": (S, "T1 explicit overturn wording (verdict line plus a line showing the goal was given/celebrated before review); "
                    "T2 VAR wording but initial decision unclear; T3 no explicit VAR text."),
        "espn_ok": (B, "Same as espn_corroborated, with blank treated as False."),
        "text_var": (B, "True if the Flashscore text contains explicit VAR / video assistant / video review wording."),
        "referee_full": (S, "On-field referee."),
    }),
    "kaggle/outputs/manual_audit_key.csv": ("Unblinded key for the manual audit: every primary-definition event in randomised order.", {
        "audit_id": (S, "Random-order identifier A001-A394."), "priority": (I, "1 = Real Madrid or one of the five clubs with most events; 2 = others."),
        "season": (S, "Season."), "fs_id": (S, "Flashscore match id."), "date": (D, "Match date."), "team": (S, "Club."), "opponent": (S, "Opponent."),
        "minute_num": (I, "Minute."), "player_full": (S, "Scorer."), "reason_fs": (S, "Reason in the feed."), "tier": (S, "Evidence tier."),
    }),
    "kaggle/outputs/manual_audit_form.csv": ("Blank reviewer form (no club or player names) to be filled from video under the protocol.", {
        "audit_id": (S, "Same id as in the key."), "date": (D, "Match date, to locate the video."), "minute_num": (I, "Minute."),
        "initial_onfield_decision": (S, "goal_given / flag_raised_before_goal / whistle_before_goal / unclear (reviewer fills)."),
        "var_action": (S, "check_only / review_overturn / review_confirmed_on_field_decision / other."),
        "final_decision": (S, "no_goal / goal."), "final_reason": (S, "offside / foul / handball / other."),
        "event_meets_protocol": (S, "Y or N: the incident meets the inclusion rules and the event definition in section 6 of the PDF."),
        "subtype": (S, "A given then overturned / B disallowed on field then checked by VAR / C other."),
        "reviewer_id": (S, "Reviewer code."), "video_source": (S, "Clip identifier or URL."),
        "second_reviewer_meets_protocol": (S, "Independent second reviewer's event_meets_protocol (Y or N)."),
        "second_reviewer_subtype": (S, "Independent second reviewer's subtype."),
        "disagreement_resolution": (S, "How a disagreement was resolved."), "notes": (S, "Free text."),
    }),
}


def check():
    rows = []
    for path, (desc, cols) in TABLES.items():
        df = pd.read_csv(ROOT / path, nrows=5, encoding="utf-8-sig")
        missing, extra = set(df.columns) - set(cols), set(cols) - set(df.columns)
        assert not missing and not extra, f"{path}: undocumented {missing}, unknown {extra}"
        for c in df.columns:
            rows.append(dict(table=path, column=c, type=cols[c][0], description=cols[c][1]))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out = check()
    out.to_csv(HERE / "data_dictionary.csv", index=False, encoding="utf-8-sig")
    print(f"{len(out)} columns documented across {out.table.nunique()} tables")
