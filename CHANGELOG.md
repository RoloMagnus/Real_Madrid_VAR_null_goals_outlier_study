# Changelog

History of the Real Madrid VAR-nullified goals project. Dates are local (US Central). Commits before 2026-10-14 were made by the project author and the daily auto-push task.

## 2026-10-15 - Pipeline audit after a reader comment
- A Medium reader argued that a clean pipeline can carry bad state (wrong minute, non-existent VAR review, merged match). Audited all three error types against the raw feeds. Full write-up: `AUDIT.md`; reproducible scripts: `scripts/audit/`; output table `data/processed/audit_event_evidence.csv`.
- Result: the four rows cited were errors of the hand-built validation sample, not of the pipeline. The audit nevertheless found five small defects (one non-VAR event counted as VAR, two weakly evidenced events, a foul-zone mis-merge, missing Understat aliases for Huesca/Oviedo, an abandoned match counted as 0-0). Real Madrid's count stays 50; the largest change in any headline estimate when the fixes are applied in an isolated copy is 0.05.
- Decision: fixes documented, **not applied**; no published number changed. The article PDF gained Section 4.5 and Appendix D and corrected two statements (the Alaves-Valencia duplicate explanation, the cause of the missing xG/PPDA). A misleading comment in `scripts/09_fouls_espn.py` was corrected (no code change).

## 2026-10-14 - Repository audit and change log
- Added this `CHANGELOG.md` to keep a readable history alongside the git log.
- Checked the daily auto-push task (`RealMadridVAR_DailyGitPush`, 11:00 PM): it ran on 10-13 (pushed 61 files) and on 10-14 (no changes to push), exit code 0. `main` is in sync with `origin/main`.
- No analysis, data or report content changed today.
- Flagged for follow-up: `article/Claude Setup.exe` (6.8 MB installer) was committed by the 10-13 auto-push and is not part of the project; consider removing it from the repository.

## 2026-10-13 - Article, Kaggle package and auto-push
- `57393fb` Daily update: 61 files. Added the `kaggle/` package (README, `reproduce.py`, `make_figures.py`, `build_pdf.py`, data dictionary, `Real_Madrid_VAR_null_goals_Kaggle.pdf`, 15 output tables/JSON and 6 figures covering definition sensitivity, club-adjusted effects, ascertainment what-if, referee heterogeneity, title scenarios, manual audit form) and supporting images and tables for the article under `article/`.
- `b554726` Daily update: `.gitignore` now excludes `data/daily_push.log`.
- `337ce39` Daily update: article draft PDF (`article/Real_Madrid_VAR_null_goals_article_draft.pdf`, 28 pages, 22 figures, 22 tables), `article.html`, article figures, `supporting_stats.json`, `scripts/daily_git_push.ps1`; EDA notebook title edited by the author.
- Scheduled task `RealMadridVAR_DailyGitPush` registered (daily 11:00 PM; commits and pushes only when files changed; refuses files over 50 MB; never force-pushes).

## 2026-10-12 - Initial release
- `2ba983f` Real Madrid VAR-nullified goals outlier case study (La Liga 2018-2026): validation of the original post, 50-goal breakdown with manual validation flags and video links, statistical framework, EDA notebook (`Real Madrid VAR - EDA.ipynb`), title scenario analysis and the Excel report (13 sheets), plus the pipeline scripts in `scripts/` and processed data in `data/processed/`. Raw crawler caches (about 1.6 GB) are excluded by `.gitignore`.
