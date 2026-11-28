"""
Shared chart style for every Python figure (and mirrored in powerbi/clouddesk_theme.json).

Categorical order is fixed and validated for colour-vision deficiency (CVD) separation
(dataviz validator: all hard checks pass on a white surface). Several hues sit below 3:1
contrast against white, so charts use direct labels / value labels as the secondary encoding.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "warehouse" / "saas.duckdb"
FIG = ROOT / "reports" / "figures"
TABLES = ROOT / "reports" / "tables"
MARTS_OUT = ROOT / "data" / "marts"

SERIES = ["#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17"]
NAVY = "#1F3B5C"          # brand accent (titles, single-series emphasis)
TEXT = "#191919"
TEXT_2 = "#666666"
GRID = "#e6e6e6"
GOOD, WARNING, SERIOUS, CRITICAL = "#0aac23", "#fbb315", "#f18a59", "#dc3c3d"
NEUTRAL = "#9aa4ae"
BLUE_RAMP = ["#cce3fd", "#9dc8f7", "#6aabf1", "#338ced", "#2370cd", "#1757ac", "#0e3d7e"]
SEQ_BLUE = LinearSegmentedColormap.from_list("seq_blue", BLUE_RAMP)
DIVERGING = LinearSegmentedColormap.from_list("div", ["#1757ac", "#84b9f3", "#efefef", "#f39a9b", "#c22f30"])

# fixed entity -> colour mapping (colour follows the entity, never its rank)
CHANNEL_COLORS = dict(zip(["organic", "paid_search", "paid_social", "referral", "content", "partner"], SERIES))
PLAN_COLORS = {"Starter": SERIES[0], "Pro": SERIES[1], "Business": SERIES[2]}
RISK_COLORS = {"Low": GOOD, "Medium": WARNING, "High": CRITICAL}
LABEL = {"organic": "Organic", "paid_search": "Paid search", "paid_social": "Paid social",
         "referral": "Referral", "content": "Content", "partner": "Partner"}


def apply():
    plt.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.titlesize": 12.5, "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 22,
        "axes.titlecolor": TEXT, "axes.labelcolor": TEXT_2, "axes.edgecolor": "#bdbdbd",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.axisbelow": True, "xtick.color": TEXT_2, "ytick.color": TEXT_2,
        "legend.frameon": False, "lines.linewidth": 2.0,
        "axes.prop_cycle": matplotlib.cycler(color=SERIES),
    })


def subtitle(ax, text):
    """Grey question line under the title, wrapped to the panel width (title pad grows to fit). Call after set_title."""
    import textwrap
    width_in = ax.get_position().width * ax.figure.get_figwidth()
    lines = textwrap.wrap(text, width=max(30, int(width_in * 14.5)))
    ax.text(0, 1.015, "\n".join(lines), transform=ax.transAxes, fontsize=9.5, color=TEXT_2, va="bottom")
    ax.set_title(ax.get_title(loc="left"), loc="left", pad=22 + 13 * (len(lines) - 1))


def footnote(fig, text="Source: synthetic data for the fictional company CloudDesk (Jan 2024 - Dec 2025).", y=-0.02):
    fig.text(0.01, y, text, fontsize=8, color=TEXT_2, ha="left", va="top")


def end_labels(ax, x, values: dict, fmt=lambda k, v: k, min_gap_frac=0.045, **kw):
    """Direct labels at the right end of lines, nudged apart so they never overlap."""
    lo, hi = ax.get_ylim()
    gap = (hi - lo) * min_gap_frac
    items = sorted(values.items(), key=lambda kv: kv[1])
    placed = []
    for k, v in items:
        y = v if not placed or v - placed[-1] >= gap else placed[-1] + gap
        placed.append(y)
        ax.text(x, y, fmt(k, v), va="center", fontsize=8.5, color=TEXT, **kw)


def save(fig, name, folder=""):
    out = FIG / folder
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.png", facecolor="white")
    plt.close(fig)
    return out / f"{name}.png"


def money(x, _=None):
    if x < 0:
        return "-" + money(-x)
    if abs(x) >= 1e6:
        return f"${x / 1e6:.1f}M"
    if abs(x) >= 1e4:
        return f"${x / 1e3:.0f}K"
    if abs(x) >= 1e3:
        return f"${x / 1e3:.1f}K"
    return f"${x:.0f}"
