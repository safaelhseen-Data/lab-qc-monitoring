"""
Control chart for a lab test, read directly from the PostgreSQL database lab_qc.

Usage:
    python control_chart.py                 -> flash_point (default)
    python control_chart.py viscosity       -> any test_code from the tests table

Output:
    charts/<test_code>_control_chart.png
    charts/<test_code>_alarms.csv
"""
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# ---------------------------------------------------------------- settings
DB_USER = os.environ.get("LAB_DB_USER", "postgres")
DB_PASSWORD = os.environ.get("LAB_DB_PASSWORD", "")   # set it in your shell, never commit it
DB_HOST = os.environ.get("LAB_DB_HOST", "localhost")
DB_PORT = int(os.environ.get("LAB_DB_PORT", "5432"))
DB_NAME = os.environ.get("LAB_DB_NAME", "lab_qc")

# Limits are calculated from this "known good" period only (before the drift starts)
BASELINE_END = "2026-08-30"
RUN_LENGTH = 7                     # rule 2: N points in a row on one side of the mean


# ---------------------------------------------------------------- data
def load_data(test_code: str) -> pd.DataFrame:
    url = URL.create(
        "postgresql+psycopg",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
    )
    engine = create_engine(url)
    query = text(
        """
        SELECT sample_id, sample_date, value, unit, min_limit, max_limit
        FROM v_results_checked
        WHERE test_code = :t
        """
    )
    return pd.read_sql(query, engine, params={"t": test_code})


# ---------------------------------------------------------------- analysis
def analyze(df: pd.DataFrame):
    """Returns (df_with_flags, stats dict)."""
    df = df.copy()
    df["sample_date"] = pd.to_datetime(df["sample_date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])                     # skip missing results
    df = df.sort_values(["sample_date", "sample_id"]).reset_index(drop=True)

    baseline = df[df["sample_date"] < pd.Timestamp(BASELINE_END)]
    mean = baseline["value"].mean()
    sd = baseline["value"].std(ddof=1)
    ucl, lcl = mean + 3 * sd, mean - 3 * sd

    # Rule 1: a single point beyond 3 sigma
    df["rule1"] = (df["value"] > ucl) | (df["value"] < lcl)

    # Rule 2: RUN_LENGTH (or more) consecutive points on the same side of the mean
    side = (df["value"] > mean).astype(int) - (df["value"] < mean).astype(int)
    run_id = (side != side.shift()).cumsum()
    run_len = side.groupby(run_id).cumcount() + 1
    df["rule2"] = (side != 0) & (run_len >= RUN_LENGTH)

    stats = {"mean": mean, "sd": sd, "ucl": ucl, "lcl": lcl}
    return df, stats


# ---------------------------------------------------------------- plot
def plot(df: pd.DataFrame, stats: dict, test_code: str, out_png: str):
    mean, sd, ucl, lcl = stats["mean"], stats["sd"], stats["ucl"], stats["lcl"]
    unit = df["unit"].iloc[0]

    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.plot(df["sample_date"], df["value"], color="#7a8ca5", lw=1, zorder=1)
    ax.scatter(df["sample_date"], df["value"], s=14, color="#3b5b8c", zorder=2, label="Result")

    only_r2 = df["rule2"] & ~df["rule1"]
    ax.scatter(df.loc[only_r2, "sample_date"], df.loc[only_r2, "value"],
               s=34, color="#f39c12", zorder=3, label=f"Rule 2: {RUN_LENGTH}+ in a row on one side")
    ax.scatter(df.loc[df["rule1"], "sample_date"], df.loc[df["rule1"], "value"],
               s=44, color="#d62728", zorder=4, label="Rule 1: beyond 3σ")

    ax.axhline(mean, color="#2e7d32", lw=1.6, label=f"Mean {mean:.2f}")
    ax.axhline(ucl, color="#d62728", ls="--", lw=1.2, label=f"UCL {ucl:.2f}")
    ax.axhline(lcl, color="#d62728", ls="--", lw=1.2, label=f"LCL {lcl:.2f}")
    ax.axhline(mean + 2 * sd, color="#999999", ls=":", lw=0.9)
    ax.axhline(mean - 2 * sd, color="#999999", ls=":", lw=0.9)

    lo, hi = df["min_limit"].iloc[0], df["max_limit"].iloc[0]
    if pd.notna(lo):
        ax.axhline(float(lo), color="black", ls="-.", lw=1, label=f"Spec min {float(lo):g}")
    if pd.notna(hi):
        ax.axhline(float(hi), color="black", ls="-.", lw=1, label=f"Spec max {float(hi):g}")

    ax.axvline(pd.Timestamp(BASELINE_END), color="#555555", ls=":", lw=1)
    ax.text(pd.Timestamp(BASELINE_END), ax.get_ylim()[1], " end of baseline",
            va="top", ha="left", fontsize=8, color="#555555")

    ax.set_title(f"Control chart: {test_code}")
    ax.set_xlabel("Sample date")
    ax.set_ylabel(unit)
    ax.grid(alpha=0.25)
    ax.legend(loc="lower left", fontsize=8, ncol=2)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    test_code = sys.argv[1] if len(sys.argv) > 1 else "flash_point"
    os.makedirs("charts", exist_ok=True)

    df = load_data(test_code)
    if df.empty:
        sys.exit(f"No data found for test_code '{test_code}'.")
    df, stats = analyze(df)

    out_png = os.path.join("charts", f"{test_code}_control_chart.png")
    plot(df, stats, test_code, out_png)

    alarms = df[df["rule1"] | df["rule2"]][["sample_id", "sample_date", "value", "rule1", "rule2"]]
    out_csv = os.path.join("charts", f"{test_code}_alarms.csv")
    alarms.to_csv(out_csv, index=False)

    print(f"Test: {test_code}   points: {len(df)}")
    print(f"Mean {stats['mean']:.2f} | SD {stats['sd']:.2f} | "
          f"LCL {stats['lcl']:.2f} | UCL {stats['ucl']:.2f}")
    print(f"Rule 1 alarms (beyond 3 sigma): {int(df['rule1'].sum())}")
    print(f"Rule 2 alarms ({RUN_LENGTH}+ in a row): {int(df['rule2'].sum())}")
    if not alarms.empty:
        print(f"First alarm: {alarms['sample_id'].iloc[0]} on "
              f"{alarms['sample_date'].iloc[0].date()}")
    print(f"Saved: {out_png}  and  {out_csv}")


if __name__ == "__main__":
    main()
