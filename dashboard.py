"""Local temperature history dashboard."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import altair as alt
import pandas as pd
import streamlit as st
from storage import load_readings

st.set_page_config(page_title="Household climate", page_icon="🌡️", layout="wide")
st.markdown("""<style>
.stApp {background:radial-gradient(ellipse at 90% 0%, #153039 0%, transparent 45%), #0b1218;}
.block-container {padding-top:2.6rem; padding-bottom:2rem; max-width:1440px;}
[data-testid="stSidebar"] {background:#101c24; border-right:1px solid #243540;}
[data-testid="stSidebar"] .block-container {padding-top:2rem;}
h1 {font-size:2.6rem !important; font-weight:650 !important; letter-spacing:-0.055em; padding-bottom:0.3rem !important;}
h3 {font-size:1.15rem !important; font-weight:600 !important; letter-spacing:-0.02em;}
[data-testid="stMetricValue"] {font-size:2.3rem; font-weight:550; letter-spacing:-0.055em; color:#eef8fc;}
[data-testid="stMetricLabel"] {font-size:0.95rem; color:#a8c1cf;}
[data-testid="stVerticalBlockBorderWrapper"] > div {border-color:#283f4b !important; border-radius:16px !important; background:linear-gradient(135deg,#162630,#101c24);}
[data-testid="stCaptionContainer"] {color:#a3b7c4;}
[data-testid="stExpander"] {border-color:#283f4b; border-radius:12px;}
.stButton > button {border-radius:9px; border-color:#35505e;}
.stButton > button:hover {border-color:#5eead4; color:#5eead4;}
.eyebrow {color:#5eead4; font-size:0.72rem; font-weight:650; letter-spacing:0.18em; margin-bottom:0.4rem;}
@media (max-width:700px) {.block-container {padding-top:1.5rem;} h1 {font-size:2rem !important;}}
</style>""", unsafe_allow_html=True)
st.markdown('<div class="eyebrow">HOME OBSERVATORY</div>', unsafe_allow_html=True)
st.title("Household climate")
st.caption("Your home, room by room. Temperature trends against the weather outside.")
st.sidebar.header("Explore")
st.sidebar.caption("Choose a window and the rooms to compare.")
hours = st.sidebar.selectbox("History", [24, 72, 168, 720], format_func=lambda n: f"{n // 24} day(s)")
st.sidebar.button("Refresh")
try:
    rows = load_readings((datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat())
except Exception:
    st.error("Cannot read Supabase. Check .env credentials and run schema.sql in Supabase first.")
    st.stop()
if not rows:
    st.info("No readings in this period. Run: uv run collect.py")
    st.stop()
df = pd.DataFrame(rows)
df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
# Prefer stable device IDs; alias keys are convenient for initial setup.
name_file = Path(__file__).with_name("device_names.json")
try:
    names = json.loads(name_file.read_text()) if name_file.exists() else {}
    if not isinstance(names, dict) or any(not isinstance(v, str) or not v.strip() for v in names.values()):
        raise ValueError("Expected a JSON object of nonempty names")
except (ValueError, OSError):
    st.warning("Could not read device_names.json; using LG aliases.")
    names = {}
labels = {}
for key, group in df.groupby("device_id"):
    alias = group.sort_values("collected_at").iloc[-1]["alias"]
    labels[key] = names.get(key, names.get(alias, alias))
# Keep devices separate if two friendly names happen to be identical.
for key, label in list(labels.items()):
    if list(labels.values()).count(label) > 1:
        for other in labels:
            if labels[other] == label:
                labels[other] = f"{label} ({other[:8]})"

selected = st.sidebar.multiselect("Equipment", list(labels), default=list(labels), format_func=labels.get)


comparison = df[df.device_id.isin(selected)].copy()
comparison["series"] = comparison["device_id"].map(labels)
comparison["temperature_c"] = pd.to_numeric(comparison["temperature"], errors="coerce")
comparison.loc[comparison.unit == "F", "temperature_c"] = (comparison.loc[comparison.unit == "F", "temperature_c"] - 32) * 5 / 9
comparison.loc[~comparison.unit.isin(["C", "F"]), "temperature_c"] = float("nan")
chart_rows = comparison[["collected_at", "series", "temperature_c"]]
if "outdoor_temperature_c" in comparison.columns:
    outdoor = comparison.copy()
    weather_times = pd.to_datetime(outdoor.get("weather_time"), utc=True, errors="coerce")
    valid = (outdoor.collected_at - weather_times).between(pd.Timedelta(0), pd.Timedelta("45min"))
    outdoor = outdoor.loc[valid].copy()
    # Plot weather at our collection time; provider time is only a freshness check.
    outdoor["temperature_c"] = pd.to_numeric(outdoor.outdoor_temperature_c, errors="coerce")
    outdoor["series"] = "Outdoor · " + outdoor["weather_location"].fillna("Weather")
    outdoor = outdoor.drop_duplicates(["collected_at", "series"])
    chart_rows = pd.concat([chart_rows, outdoor[["collected_at", "series", "temperature_c"]]], ignore_index=True)
# Compact latest-reading cards replace the repeated per-room sections.
if selected:
    cards = st.columns(min(len(selected), 4))
    for index, device_id in enumerate(selected):
        latest = comparison[comparison.device_id == device_id].sort_values("collected_at").iloc[-1]
        with cards[index % len(cards)]:
            with st.container(border=True):
                value = latest.temperature_c
                st.metric(labels[device_id], f"{value:.1f} °C" if pd.notna(value) else "Unavailable")
                age = max(0, int((datetime.now(timezone.utc) - latest.collected_at.to_pydatetime()).total_seconds() / 60))
                power = {"POWER_ON": "Cooling on", "POWER_OFF": "AC off"}.get(latest.power, "Unknown power")
                if latest.power == "POWER_ON" and latest.get("mode") != "COOL":
                    power = "AC on"
                st.caption(f"{power} · {age} min ago" + (" · Overdue" if age > 45 else ""))
                outside = latest.get("outdoor_temperature_c")
                source = pd.to_datetime(latest.get("weather_time"), utc=True, errors="coerce")
                if pd.notna(value) and pd.notna(outside) and pd.notna(source) and pd.Timedelta(0) <= latest.collected_at - source <= pd.Timedelta("45min"):
                    st.caption(f"{value - outside:+.1f} °C vs outside")

st.subheader("Temperature over time")
st.caption("All selected rooms and outdoor weather · °C · Curitiba time (UTC−3)")
chart_rows = chart_rows.dropna(subset=["temperature_c"]).copy()
if not chart_rows.empty:
    # Use explicit UTC-tagged display coordinates so serialization cannot reinterpret
    # naive local datetimes. Real collection timestamps remain untouched in storage.
    chart_rows["local_time"] = chart_rows.collected_at.dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None).dt.tz_localize("UTC")
    chart_rows["time_label"] = chart_rows.collected_at.dt.tz_convert("America/Sao_Paulo").dt.strftime("%d %b %Y %H:%M:%S UTC−3")
    chart_rows["kind"] = chart_rows.series.map(lambda name: "Outdoor" if name.startswith("Outdoor · ") else "Room")
    domain = sorted(chart_rows.series.unique())
    palette = ["#38bdf8", "#a78bfa", "#34d399", "#fbbf24", "#fb7185", "#2dd4bf"]
    colors = ["#94a3b8" if name.startswith("Outdoor · ") else palette[i % len(palette)] for i, name in enumerate(domain)]
    # Allow larger histories without Altair's default 5,000-row limit.
    alt.data_transformers.disable_max_rows()
    focus = alt.selection_point(fields=["series"], bind="legend")
    patterns = [[1, 0], [7, 4], [2, 3], [10, 3, 2, 3], [12, 5], [4, 2]]
    base = alt.Chart(chart_rows).encode(
        x=alt.X("local_time:T", title=None, scale=alt.Scale(type="utc", padding=20), axis=alt.Axis(format="%d %b %H:%M", tickCount=6, labelAngle=0, grid=False)),
        y=alt.Y("temperature_c:Q", title="°C", scale=alt.Scale(zero=False, padding=20), axis=alt.Axis(tickCount=6, format=".1f", gridOpacity=0.12)),
        color=alt.Color("series:N", title=None, scale=alt.Scale(domain=domain, range=colors), legend=alt.Legend(orient="top", direction="horizontal", symbolType="stroke", labelLimit=240)),
        opacity=alt.condition(focus, alt.value(1), alt.value(0.12)),
        tooltip=[alt.Tooltip("time_label:N", title="Curitiba time"), alt.Tooltip("series:N", title="Location"), alt.Tooltip("temperature_c:Q", title="Temperature (°C)", format=".1f")],
    )
    lines = base.mark_line(strokeWidth=2.5, clip=True).encode(
        strokeDash=alt.StrokeDash("series:N", scale=alt.Scale(domain=domain, range=[patterns[i % len(patterns)] for i in range(len(domain))]), legend=None),
    )
    # Hollow, differently sized symbols remain distinguishable at equal coordinates.
    points = base.mark_point(filled=False, strokeWidth=2, clip=True).encode(
        shape=alt.Shape("series:N", scale=alt.Scale(domain=domain, range=["circle", "square", "diamond", "triangle-up", "cross", "triangle-down"][:len(domain)]), legend=None),
        size=alt.Size("series:N", scale=alt.Scale(domain=domain, range=[70 + i * 70 for i in range(len(domain))]), legend=None),
    )
    chart = (lines + points).add_params(focus).properties(height=400, background="#101c24").configure_view(strokeWidth=0).configure_axis(
        labelColor="#a3b7c4", titleColor="#a3b7c4", gridColor="#35505e", domain=False,
        labelFontSize=11, titleFontSize=12, labelPadding=10, tickSize=0,
    ).configure_legend(labelColor="#d5e6ee", labelFontSize=12, padding=12).interactive()
    st.altair_chart(chart, width="stretch")
    if comparison.groupby("device_id").size().max() == 1:
        st.info("One reading per room so far. Dots will become trend lines as collection continues.")
    st.caption("Distinct patterns and hollow markers separate overlapping series. Click a legend name to isolate it; Shift-click selects several, double-click resets. Outdoor model estimate from [Open-Meteo](https://open-meteo.com/). Dots are collected samples; lines may span gaps. All points use our collection time; weather source time is used only to check freshness.")
else:
    st.info("Select equipment with temperature readings to display the chart.")

with st.expander("Latest readings and history"):
    details = comparison.copy()
    details["room"] = details.device_id.map(labels)
    details["time"] = details.collected_at.dt.tz_convert("America/Sao_Paulo").dt.strftime("%d %b %Y %H:%M:%S")
    columns = ["room", "time", "temperature_c", "power", "mode", "target_temperature", "unit"]
    st.dataframe(details.sort_values("collected_at", ascending=False)[columns], hide_index=True, width="stretch")
