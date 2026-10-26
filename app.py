"""
Lab QC Dashboard (Streamlit)

Run from the project folder:
    python -m streamlit run app.py

It reuses control_chart.py (database settings + control limits logic),
so keep both files in the same folder.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

import control_chart as cc

st.set_page_config(page_title="Lab QC Dashboard", page_icon=":test_tube:", layout="wide")

GREEN, RED, ORANGE, BLUE, GREY = "#2e7d32", "#d62728", "#f39c12", "#3b5b8c", "#7a8ca5"


# ---------------------------------------------------------------- data
@st.cache_data(ttl=300)
def list_tests() -> pd.DataFrame:
    url = URL.create(
        "postgresql+psycopg",
        username=cc.DB_USER, password=cc.DB_PASSWORD,
        host=cc.DB_HOST, port=cc.DB_PORT, database=cc.DB_NAME,
    )
    engine = create_engine(url)
    return pd.read_sql(text("SELECT test_code, unit FROM tests ORDER BY test_code"), engine)


@st.cache_data(ttl=300)
def load(test_code: str) -> pd.DataFrame:
    return cc.load_data(test_code)


def spec_limits(df: pd.DataFrame):
    lo, hi = df["min_limit"].iloc[0], df["max_limit"].iloc[0]
    lo = float(lo) if pd.notna(lo) else None
    hi = float(hi) if pd.notna(hi) else None
    return lo, hi


def summarize(view: pd.DataFrame, lo, hi) -> dict:
    out_of_spec = pd.Series(False, index=view.index)
    if lo is not None:
        out_of_spec |= view["value"] < lo
    if hi is not None:
        out_of_spec |= view["value"] > hi
    return {
        "n": len(view),
        "rule1": int(view["rule1"].sum()),
        "rule2": int(view["rule2"].sum()),
        "out_of_spec": int(out_of_spec.sum()),
    }


# ---------------------------------------------------------------- chart
def build_figure(view, stats, unit, lo, hi, baseline_end):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=view["sample_date"], y=view["value"], mode="lines+markers", name="Result",
        line=dict(width=1, color=GREY), marker=dict(size=5, color=BLUE),
        customdata=view["sample_id"],
        hovertemplate="%{customdata}<br>%{x|%Y-%m-%d}<br>%{y}<extra></extra>",
    ))

    only_r2 = view[view["rule2"] & ~view["rule1"]]
    fig.add_trace(go.Scatter(
        x=only_r2["sample_date"], y=only_r2["value"], mode="markers",
        name=f"Rule 2: {cc.RUN_LENGTH}+ in a row on one side",
        marker=dict(size=9, color=ORANGE), customdata=only_r2["sample_id"],
        hovertemplate="%{customdata}<br>%{x|%Y-%m-%d}<br>%{y}<extra></extra>",
    ))
    r1 = view[view["rule1"]]
    fig.add_trace(go.Scatter(
        x=r1["sample_date"], y=r1["value"], mode="markers", name="Rule 1: beyond 3σ",
        marker=dict(size=11, color=RED), customdata=r1["sample_id"],
        hovertemplate="%{customdata}<br>%{x|%Y-%m-%d}<br>%{y}<extra></extra>",
    ))

    for label, y, color, dash in [
        ("Mean", stats["mean"], GREEN, "solid"),
        ("UCL", stats["ucl"], RED, "dash"),
        ("LCL", stats["lcl"], RED, "dash"),
    ]:
        fig.add_hline(y=y, line=dict(color=color, dash=dash, width=1.5),
                      annotation_text=f"{label} {y:.2f}", annotation_position="right")
    if lo is not None:
        fig.add_hline(y=lo, line=dict(color="black", dash="dashdot", width=1),
                      annotation_text=f"Spec min {lo:g}", annotation_position="right")
    if hi is not None:
        fig.add_hline(y=hi, line=dict(color="black", dash="dashdot", width=1),
                      annotation_text=f"Spec max {hi:g}", annotation_position="right")

    b = pd.Timestamp(baseline_end)
    if view["sample_date"].min() <= b <= view["sample_date"].max():
        fig.add_shape(type="line", x0=b, x1=b, y0=0, y1=1, yref="paper",
                      line=dict(color="grey", dash="dot", width=1))
        fig.add_annotation(x=b, y=1, yref="paper", text="end of baseline",
                           showarrow=False, xanchor="left", yanchor="top", font=dict(size=10))

    fig.update_layout(
        height=520, margin=dict(l=10, r=120, t=30, b=10),
        yaxis_title=unit, xaxis_title="Sample date",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


# ---------------------------------------------------------------- page
st.title("Lab QC Dashboard")
st.caption("Diesel fuel testing: control charts and spec compliance, read live from PostgreSQL.")

try:
    tests = list_tests()
except Exception as e:  # connection / password problems
    st.error(f"Could not connect to the database: {e}")
    st.info("Check the LAB_DB_PASSWORD environment variable (and host/port) and make sure PostgreSQL is running.")
    st.stop()

st.sidebar.header("Filters")
test_code = st.sidebar.selectbox("Test", tests["test_code"].tolist())
baseline_end = st.sidebar.date_input(
    "Baseline ends on",
    value=pd.Timestamp(cc.BASELINE_END).date(),
    help="Control limits are calculated from results BEFORE this date (the known-good period).",
)
cc.BASELINE_END = baseline_end.isoformat()

raw = load(test_code)
if raw.empty:
    st.warning(f"No results for '{test_code}'.")
    st.stop()

df, stats = cc.analyze(raw)
unit = df["unit"].iloc[0]
lo, hi = spec_limits(df)

min_d, max_d = df["sample_date"].min().date(), df["sample_date"].max().date()
period = st.sidebar.date_input("Period", value=(min_d, max_d), min_value=min_d,
                               max_value=max_d, key=f"period_{test_code}")
if not isinstance(period, (tuple, list)) or len(period) != 2:
    st.info("Pick both a start and an end date.")
    st.stop()

view = df[(df["sample_date"] >= pd.Timestamp(period[0])) &
          (df["sample_date"] <= pd.Timestamp(period[1]))]
if view.empty:
    st.warning("No results in this period.")
    st.stop()

s = summarize(view, lo, hi)
last = view.iloc[-1]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Results shown", s["n"])
c2.metric("Beyond 3σ (Rule 1)", s["rule1"])
c3.metric(f"{cc.RUN_LENGTH}+ in a row (Rule 2)", s["rule2"])
c4.metric("Out of spec", s["out_of_spec"])
c5.metric("Last result", f"{last['value']:g}", f"{last['value'] - stats['mean']:+.2f} vs mean",
          delta_color="off")

st.subheader(f"Control chart: {test_code}")
st.plotly_chart(build_figure(view, stats, unit, lo, hi, cc.BASELINE_END), use_container_width=True)
st.caption(
    f"Baseline mean {stats['mean']:.2f} {unit}, SD {stats['sd']:.2f}, "
    f"LCL {stats['lcl']:.2f}, UCL {stats['ucl']:.2f}."
)

st.subheader("Alarms")
alarms = view[view["rule1"] | view["rule2"]].copy()
if alarms.empty:
    st.success("No alarms in this period.")
else:
    alarms["alarm"] = ["Beyond 3σ" if r1 else f"{cc.RUN_LENGTH}+ in a row" for r1 in alarms["rule1"]]
    alarms["sample_date"] = alarms["sample_date"].dt.date
    table = alarms[["sample_id", "sample_date", "value", "alarm"]]
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.download_button("Download alarms (CSV)", table.to_csv(index=False).encode("utf-8"),
                       file_name=f"{test_code}_alarms.csv", mime="text/csv")
