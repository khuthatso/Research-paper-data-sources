#!/usr/bin/env python3
"""
Analysis of the pointer-chasing cache-latency measurements.

Reads data/run1.csv, data/run2.csv, data/run3.csv (columns: size_bytes, run, ns_per_access)
and writes tables, a text summary and Figure 2 to results/.

Rules (paper Sections 2.5 and 2.8), fixed BEFORE the estimates were calculated:
  * Per size, per session: median, minimum, maximum of the 7 timed runs.
  * Step = ratio of consecutive medians >= threshold (main threshold 1.5;
    sensitivity checks 1.3 and 2.0). If consecutive pairs both qualify, they count
    as ONE transition that starts at the first pair.
  * A transition is reported as a bracket (largest size before the step, next size).
  * Each bracket is compared with the published cache sizes (AMD) in two ways:
    does the published size lie inside the bracket, and the ratio of the bracket's
    lower bound to the published size.
  * Repeatability: relative difference of the medians of run 2 and run 3,
    |a - b| / mean(a, b), summarised by its median and maximum.
  * Power-state effect: median of run 1 divided by the mean of the run 2 and run 3 medians.

Usage (from the repository root):
    python analysis/analyze.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "results"

RUNS = {"run1": "Run 1 (unplugged)", "run2": "Run 2", "run3": "Run 3"}
MAIN_THRESHOLD = 1.5
THRESHOLDS = (MAIN_THRESHOLD, 1.3, 2.0)          # main rule + sensitivity checks
PUBLISHED = {                                      # manufacturer's published sizes (AMD n.d.)
    "L1 data (32 KB)": 32 * 1024,
    "L2 (512 KB)": 512 * 1024,
    "L3 (8 MB)": 8 * 1024 ** 2,
}
EXPECTED_SIZES = 33
EXPECTED_REPEATS = 7


def label(n_bytes: float) -> str:
    n_bytes = int(n_bytes)
    if n_bytes >= 1024 ** 2:
        return f"{n_bytes / 1024 ** 2:g} MB"
    return f"{n_bytes / 1024:g} KB"


def load_run(name: str) -> pd.DataFrame:
    df = pd.read_csv(DATA / f"{name}.csv")
    sizes = df["size_bytes"].nunique()
    repeats = df.groupby("size_bytes").size().unique()
    if sizes != EXPECTED_SIZES or list(repeats) != [EXPECTED_REPEATS] or df.isna().any().any():
        raise ValueError(f"{name}.csv is not complete: {sizes} sizes, repeats per size {list(repeats)}")
    return df


def per_size_stats(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("size_bytes")["ns_per_access"]
    out = pd.DataFrame({"median": g.median(), "min": g.min(), "max": g.max()})
    out["spread_pct"] = 100 * (out["max"] - out["min"]) / out["median"]
    return out


def detect_steps(median: pd.Series, threshold: float) -> list[dict]:
    """Transitions where the ratio of consecutive medians is >= threshold."""
    sizes = median.index.to_numpy()
    values = median.to_numpy()
    ratios = values[1:] / values[:-1]
    qualifies = ratios >= threshold
    steps, i = [], 0
    while i < len(qualifies):
        if qualifies[i]:
            j = i
            while j + 1 < len(qualifies) and qualifies[j + 1]:
                j += 1
            steps.append({
                "lower_bytes": int(sizes[i]),
                "upper_bytes": int(sizes[i + 1]),
                "ratio": float(ratios[i]),
                "merged_pairs": j - i + 1,
            })
            i = j + 1
        else:
            i += 1
    return steps


def compare_with_published(steps: list[dict]) -> list[dict]:
    rows = []
    for name, size in PUBLISHED.items():
        inside = [s for s in steps if s["lower_bytes"] <= size <= s["upper_bytes"]]
        if inside:
            s, contained = inside[0], True
        elif steps:
            s = min(steps, key=lambda t: abs(np.log2(t["lower_bytes"] / size)))
            contained = False
        else:
            rows.append({"cache": name, "published_bytes": size, "bracket": "none detected",
                         "published_inside_bracket": False, "lower_over_published": np.nan})
            continue
        rows.append({
            "cache": name,
            "published_bytes": size,
            "bracket": f"{label(s['lower_bytes'])} - {label(s['upper_bytes'])}",
            "published_inside_bracket": contained,
            "lower_over_published": s["lower_bytes"] / size,
        })
    return rows


def make_figure(stats: dict[str, pd.DataFrame]) -> None:
    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=300)
    style = {"run1": ("#B0413E", "s"), "run2": ("#1F5FA8", "o"), "run3": ("#2E8B57", "^")}
    for key, (color, marker) in style.items():
        s = stats[key]
        ax.fill_between(s.index, s["min"], s["max"], color=color, alpha=0.12, linewidth=0)
        ax.plot(s.index, s["median"], marker=marker, ms=4.5, lw=1.4, color=color,
                label=f"{RUNS[key]}: median, band = min-max of {EXPECTED_REPEATS} runs")
    for name, size in PUBLISHED.items():
        ax.axvline(size, color="black", ls="--", lw=1, alpha=0.7)
        ax.text(size * 1.04, 1.8, name.replace(" (", "\n(") + " spec", fontsize=8, va="bottom")
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.xaxis.set_major_locator(FixedLocator([2 ** e for e in range(12, 29, 2)]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: label(v)))
    ax.yaxis.set_major_locator(FixedLocator([2, 3, 5, 10, 20, 50, 100, 200]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
    ax.minorticks_off()
    ax.set_ylim(1.5, 320)
    ax.set_xlabel("Working-set size (log scale)")
    ax.set_ylabel("Latency per access (ns, log scale)")
    ax.grid(True, which="major", alpha=0.3)
    ax.legend(loc="upper left", fontsize=8.5)
    fig.savefig(OUT / "figure2_latency_vs_size.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    stats = {k: per_size_stats(load_run(k)) for k in RUNS}

    # ---- per-size summary table ------------------------------------------------
    table = pd.DataFrame(index=stats["run1"].index)
    table.insert(0, "size", [label(s) for s in table.index])
    for k, s in stats.items():
        table[f"{k}_median_ns"] = s["median"]
        table[f"{k}_min_ns"] = s["min"]
        table[f"{k}_max_ns"] = s["max"]
        table[f"{k}_spread_pct"] = s["spread_pct"]
    a, b = stats["run2"]["median"], stats["run3"]["median"]
    table["run2_vs_run3_rel_diff_pct"] = 100 * (a - b).abs() / ((a + b) / 2)
    table["run1_over_mean_run2_run3"] = stats["run1"]["median"] / ((a + b) / 2)
    table.round(4).to_csv(OUT / "per_size_summary.csv")

    # ---- step detection and comparison with published sizes ---------------------
    step_rows, cmp_rows = [], []
    for k in RUNS:
        for thr in THRESHOLDS:
            steps = detect_steps(stats[k]["median"], thr)
            for n, s in enumerate(steps, 1):
                step_rows.append({"run": k, "threshold": thr, "step_no": n,
                                  "bracket": f"{label(s['lower_bytes'])} - {label(s['upper_bytes'])}",
                                  **s})
            for r in compare_with_published(steps):
                cmp_rows.append({"run": k, "threshold": thr, **r})
    steps_df = pd.DataFrame(step_rows)
    cmp_df = pd.DataFrame(cmp_rows)
    steps_df.round(3).to_csv(OUT / "step_detection.csv", index=False)
    cmp_df.round(3).to_csv(OUT / "published_comparison.csv", index=False)

    # ---- text summary -----------------------------------------------------------
    d = table["run2_vs_run3_rel_diff_pct"]
    ratio = table["run1_over_mean_run2_run3"]
    lines = [
        "SUMMARY OF ANALYSIS",
        "=" * 60,
        f"Main threshold: {MAIN_THRESHOLD}  (sensitivity: {THRESHOLDS[1]} and {THRESHOLDS[2]})",
        "",
        "Repeatability, run 2 vs run 3 (relative difference of medians, all 33 sizes)",
        f"  median: {d.median():.1f} %    maximum: {d.max():.1f} % at {table.loc[d.idxmax(), 'size']}",
        "",
        "Power-state effect, run 1 / mean(run 2, run 3)",
        f"  4-16 KB (L1 region): {ratio.iloc[:5].mean():.2f}",
        f"  256 MB (largest size): {ratio.iloc[-1]:.2f}",
        f"  all sizes: min {ratio.min():.2f}, median {ratio.median():.2f}, max {ratio.max():.2f}",
        "",
        "Transitions found (bracket = largest size before the step - next size)",
    ]
    for k in RUNS:
        for thr in THRESHOLDS:
            sub = steps_df[(steps_df.run == k) & (steps_df.threshold == thr)]
            br = ", ".join(sub["bracket"]) if len(sub) else "none"
            lines.append(f"  {RUNS[k]:<18} threshold {thr}: {br}")
    lines += ["", "Comparison with published sizes (main threshold)"]
    for k in RUNS:
        sub = cmp_df[(cmp_df.run == k) & (cmp_df.threshold == MAIN_THRESHOLD)]
        for _, r in sub.iterrows():
            lines.append(f"  {RUNS[k]:<18} {r['cache']:<16} nearest bracket {r['bracket']:<16} "
                         f"inside: {str(r['published_inside_bracket']):<5} lower/published: {r['lower_over_published']:.3f}")
    text = "\n".join(lines)
    (OUT / "summary.txt").write_text(text + "\n", encoding="utf-8")
    print(text)

    make_figure(stats)
    print(f"\nFiles written to {OUT}")


if __name__ == "__main__":
    main()
