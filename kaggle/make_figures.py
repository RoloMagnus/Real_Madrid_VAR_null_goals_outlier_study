"""Figures for the Kaggle PDF; reads the tables written by reproduce.py. Run: python kaggle/make_figures.py"""
import json
from pathlib import Path

import matplotlib
import matplotlib.ticker
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent / "outputs"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
NAVY, RED, GREY = "#1F3864", "#C00000", "#8C8C8C"
plt.rcParams.update({"font.size": 9, "axes.titleweight": "bold", "axes.spines.top": False, "axes.spines.right": False})


def forest(ax, labels, est, lo, hi, color, highlight=None, ref=1.0):
    y = list(range(len(labels)))[::-1]
    for yi, e, l, h, lab in zip(y, est, lo, hi, labels):
        c = RED if lab == highlight else color
        ax.plot([l, h], [yi, yi], color=c, lw=1.6)
        ax.plot(e, yi, "o", color=c, ms=5)
    ax.axvline(ref, color=GREY, ls="--", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xscale("log")
    ax.set_xlim(0.22, 3.6)
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_xticks([0.25, 0.5, 1, 2, 3])
    ax.set_xticklabels(["0.25", "0.5", "1", "2", "3"])


def goals_table():
    """Appendix-C style table of the 50 Real Madrid goals (data/processed/RM_nullified_goals_breakdown.csv)."""
    import textwrap
    from matplotlib.patches import Rectangle

    b = pd.read_csv(OUT.parents[1] / "data" / "processed" / "RM_nullified_goals_breakdown.csv", encoding="utf-8-sig")
    heads = ["#", "Date", "Rd", "Rival", "Scorer", "Min", "Reason", "Context", "V", "Score", "Result", "Pos.", "Referee"]
    wid = [0.03, 0.075, 0.03, 0.085, 0.095, 0.035, 0.085, 0.145, 0.025, 0.045, 0.055, 0.04, 0.17]
    wrap = [0, 0, 0, 11, 13, 0, 13, 22, 0, 0, 0, 0, 22]
    rows = []
    for r in b.itertuples(index=False):
        d = r._asdict() if hasattr(r, "_asdict") else {}
        vals = [r.rank, str(r.date)[:10], int(r.round), r.rival, r.active_player, int(r.minute), r.var_reason, r.context_category,
                "H" if r.local_flag else "A", f"{r.team_goals_final}-{r.rival_goals_final}", r.outcome, int(r.league_position_at_time) if pd.notna(r.league_position_at_time) else "",
                r.referee_on_field]
        rows.append(["\n".join(textwrap.wrap(str(v), w)) if w else str(v) for v, w in zip(vals, wrap)])
    heights = [max(s.count("\n") + 1 for s in row) for row in rows]
    unit = 0.0158
    W, hdr = 15.0, 0.9
    total = sum(h * unit * 1.0 + 0.0045 for h in heights)
    fig_h = (total + 0.075) * W * 0.72 + 1.6
    fig = plt.figure(figsize=(W * 0.72, fig_h))
    ax = fig.add_axes([0.02, 0.01, 0.96, 0.90])
    ax.set_xlim(0, sum(wid))
    ax.set_ylim(total + 0.03, 0)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), sum(wid), 0.03, color="#1F3864"))
    x = 0
    for h, w in zip(heads, wid):
        ax.text(x + 0.004, 0.015, h, color="white", fontweight="bold", va="center", fontsize=8.5)
        x += w
    y = 0.03
    for i, (row, nh) in enumerate(zip(rows, heights)):
        rh = nh * unit + 0.0045
        if i % 2:
            ax.add_patch(Rectangle((0, y), sum(wid), rh, color="#F3F5FA", lw=0))
        ax.plot([0, sum(wid)], [y + rh, y + rh], color="#D8DCE6", lw=0.4)
        x = 0
        for v, w in zip(row, wid):
            ax.text(x + 0.004, y + 0.0035, v, va="top", fontsize=7.6, linespacing=1.15)
            x += w
        y += rh
    fig.text(0.02, 0.965, "The 50 Real Madrid VAR-nullified goals, La Liga 2018-19 to 12 October 2026", fontsize=13, fontweight="bold", color="#1F3864")
    fig.text(0.02, 0.945, "Round, venue (H/A), final score and result from Real Madrid's perspective, league position at kick-off. All 50 checked against video by the study team.",
             fontsize=7.8, color="#444444")
    fig.savefig(FIG / "k4_rm_50_goals.png", dpi=200)
    plt.close(fig)


def goals_table_parts(parts=((0, 25), (25, 50)), fs=10.5, width_in=11.0):
    """Medium-friendly version: the 50 goals in several images with larger type (coordinates in inches)."""
    import textwrap
    from matplotlib.patches import Rectangle

    b = pd.read_csv(OUT.parents[1] / "data" / "processed" / "RM_nullified_goals_breakdown.csv", encoding="utf-8-sig")
    heads = ["#", "Date", "Rd", "Rival", "Scorer", "Min", "Reason", "Context", "V", "Score", "Result", "Pos.", "Referee"]
    cw = [0.32, 0.92, 0.36, 1.05, 1.12, 0.42, 1.3, 1.65, 0.3, 0.55, 0.68, 0.46, 1.9]
    wrap = [0, 0, 0, 10, 12, 0, 14, 20, 0, 0, 0, 0, 22]
    scale = width_in / sum(cw)
    cw = [c * scale for c in cw]
    line_h, pad = fs * 1.2 / 72, 0.07
    rows = []
    for r in b.itertuples(index=False):
        vals = [r.rank, str(r.date)[:10], int(r.round), r.rival, r.active_player, int(r.minute), r.var_reason, r.context_category,
                "H" if r.local_flag else "A", f"{r.team_goals_final}-{r.rival_goals_final}", r.outcome,
                int(r.league_position_at_time) if pd.notna(r.league_position_at_time) else "", r.referee_on_field]
        rows.append(["\n".join(textwrap.wrap(str(v), w)) if w else str(v) for v, w in zip(vals, wrap)])
    for k, (a, z) in enumerate(parts):
        sub = rows[a:z]
        hs = [max(c.count("\n") + 1 for c in row) * line_h + 2 * pad for row in sub]
        head_h, top_h = line_h + 2 * pad + 0.05, 0.75 if k == 0 else 0.45
        fig_h = top_h + head_h + sum(hs) + 0.15
        fig = plt.figure(figsize=(width_in + 0.4, fig_h))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(-0.2, width_in + 0.2)
        ax.set_ylim(fig_h, 0)
        ax.axis("off")
        if k == 0:
            ax.text(0, 0.28, "The 50 Real Madrid VAR-nullified goals, La Liga 2018-19 to 12 October 2026", fontsize=fs + 3, fontweight="bold", color=NAVY)
            ax.text(0, 0.55, "Venue (H/A), final score and result from Real Madrid's perspective; league position at kick-off.", fontsize=fs - 2, color="#444444")
        else:
            ax.text(0, 0.28, f"The 50 Real Madrid VAR-nullified goals (continued, #{a + 1}-{z})", fontsize=fs + 1, fontweight="bold", color=NAVY)
        y = top_h
        ax.add_patch(Rectangle((0, y), width_in, head_h, color=NAVY))
        x = 0
        for h, w in zip(heads, cw):
            ax.text(x + 0.06, y + head_h / 2, h, color="white", fontweight="bold", va="center", fontsize=fs)
            x += w
        y += head_h
        for i, (row, rh) in enumerate(zip(sub, hs)):
            if i % 2:
                ax.add_patch(Rectangle((0, y), width_in, rh, color="#F3F5FA", lw=0))
            ax.plot([0, width_in], [y + rh, y + rh], color="#D8DCE6", lw=0.5)
            x = 0
            for v, w in zip(row, cw):
                ax.text(x + 0.06, y + pad, v, va="top", fontsize=fs, linespacing=1.2)
                x += w
            y += rh
        fig.savefig(FIG / f"k4_rm_50_goals_part{k + 1}.png", dpi=170)
        plt.close(fig)


def main():
    goals_table()
    goals_table_parts()
    ds = pd.read_csv(OUT / "definition_sensitivity.csv")
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    lab = [f"{r.key}  ({r.rm_events} vs {r.others_events})" for r in ds.itertuples()]
    y = list(range(len(ds)))[::-1]
    for yi, r in zip(y, ds.itertuples()):
        ax.plot([r.rr_lo, r.rr_hi], [yi + 0.15, yi + 0.15], color=GREY, lw=1.4)
        ax.plot(r.rate_ratio, yi + 0.15, "s", color=GREY, ms=4)
        ax.plot([r.adj_lo, r.adj_hi], [yi - 0.15, yi - 0.15], color=NAVY, lw=1.4)
        ax.plot(r.adj_irr, yi - 0.15, "o", color=NAVY, ms=4.5)
    ax.axvline(1, color=GREY, ls="--", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(lab)
    ax.set_xscale("log")
    ax.set_xticks([1, 2, 3, 4, 5])
    ax.set_xticklabels(["1", "2", "3", "4", "5"])
    ax.set_xlabel("Rate ratio, Real Madrid vs other clubs (95% CI)")
    ax.plot([], [], "s", color=GREY, label="Unadjusted rate ratio (per match)")
    ax.plot([], [], "o", color=NAVY, label="Adjusted IRR (offsides, shots, xG, home, season)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, frameon=False, fontsize=8)
    ax.set_title("Event definition and sample restrictions")
    fig.tight_layout()
    fig.savefig(FIG / "k1_definition_sensitivity.png", dpi=170)
    plt.close(fig)

    ce = pd.read_csv(OUT / "club_adjusted_effects.csv").sort_values("irr")
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    forest(ax, ce.team.tolist(), ce.irr, ce.lo, ce.hi, NAVY, highlight="Real Madrid")
    ax.set_xlabel("Adjusted IRR vs clubs other than Real Madrid (95% CI, clubs with >= 100 matches)")
    ax.set_title("Adjusted rate of recorded VAR-nullified goals by club")
    fig.tight_layout()
    fig.savefig(FIG / "k2_club_effects.png", dpi=170)
    plt.close(fig)

    ab = pd.read_csv(OUT / "ascertainment_what_if.csv")
    fig, axs = plt.subplots(1, 2, figsize=(7.4, 3.2), sharey=True)
    for ax, mask, xl in ((axs[0], ab.scenario.str.startswith("Other"), "Other clubs' true events as a multiple of recorded (c)"),
                         (axs[1], ab.scenario.str.contains("not true"), "Real Madrid events that are not true overturns (of 50)")):
        s = ab[mask]
        ax.fill_between(s.assumption, s.lo, s.hi, color=NAVY, alpha=0.15)
        ax.plot(s.assumption, s.irr, "o-", color=NAVY)
        ax.axhline(1, color=GREY, ls="--", lw=0.8)
        ax.set_xlabel(xl)
    axs[0].set_ylabel("Adjusted IRR after rescaling")
    fig.suptitle("Assumption-based what-if: how much differential recording would erase the adjusted excess?", fontsize=9, fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "k3_ascertainment_what_if.png", dpi=170)
    plt.close(fig)
    print("figures written to", FIG)


if __name__ == "__main__":
    main()
