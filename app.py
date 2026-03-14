"""
F1 Race Engineer Dashboard
A comprehensive dashboard for F1 race analysis, telemetry, and AI-powered insights.
"""

import json
import threading
import time
import warnings
from pathlib import Path

import anthropic
import fastf1
from fastf1.livetiming.client import SignalRClient
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats
import streamlit as st

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

COMPOUND_COLORS = {
    "SOFT": "#FF3333",
    "MEDIUM": "#FFC300",
    "HARD": "#FFFFFF",
    "INTERMEDIATE": "#39B54A",
    "WET": "#0067FF",
    "UNKNOWN": "#888888",
}

TEAM_COLORS = {
    "Red Bull Racing": "#3671C6",
    "Ferrari": "#E8002D",
    "Mercedes": "#27F4D2",
    "McLaren": "#FF8000",
    "Aston Martin": "#229971",
    "Alpine": "#FF87BC",
    "Williams": "#64C4FF",
    "AlphaTauri": "#6692FF",
    "RB": "#6692FF",
    "Alfa Romeo": "#C92D4B",
    "Haas F1 Team": "#B6BABD",
    "Kick Sauber": "#52E252",
    "Sauber": "#52E252",
}

st.set_page_config(page_title="F1 Race Engineer Dashboard", layout="wide")

# Dark theme CSS
st.markdown(
    """
    <style>
    .stApp { background-color: #0E1117; }
    .metric-card {
        background: #1A1D23; border-radius: 10px; padding: 20px;
        border: 1px solid #2D3139; margin: 5px 0;
    }
    .metric-card h3 { color: #FAFAFA; margin: 0 0 8px 0; font-size: 14px; }
    .metric-card p { color: #E0E0E0; margin: 0; font-size: 24px; font-weight: bold; }
    .debrief-card {
        background: #1A1D23; border-radius: 10px; padding: 24px;
        border: 1px solid #2D3139; line-height: 1.7; color: #E0E0E0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

st.sidebar.title("F1 Race Engineer")
year = st.sidebar.selectbox("Year", [2026, 2025, 2024, 2023, 2022], index=0)


@st.cache_data(show_spinner=False)
def get_event_names(yr: int):
    schedule = fastf1.get_event_schedule(yr)
    events = schedule[schedule["EventFormat"] != "testing"]
    return events["EventName"].tolist()


try:
    events = get_event_names(year)
    gp_name = st.sidebar.selectbox("Grand Prix", events, index=0)
except Exception:
    gp_name = st.sidebar.text_input("Grand Prix", value="Australia")

session_type = st.sidebar.selectbox("Session", ["Race", "Qualifying", "Sprint"])

load_btn = st.sidebar.button("Load Session", type="primary", use_container_width=True)
st.sidebar.caption("First load for a GP downloads data from the F1 API and may take 30-60s. Subsequent loads are cached.")


# ---------------------------------------------------------------------------
# Session loading
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Loading session data...")
def load_session(year: int, gp: str, session: str):
    sess = fastf1.get_session(year, gp, session[0])  # "R", "Q", "S"
    sess.load()
    return sess


if load_btn or "session" in st.session_state:
    if load_btn:
        try:
            st.session_state["session"] = load_session(year, gp_name, session_type)
            st.session_state["params"] = (year, gp_name, session_type)
        except Exception as e:
            st.error(f"Failed to load session: {e}")
            st.stop()

    session = st.session_state["session"]
    laps = session.laps
    results = session.results
    drivers = laps["Driver"].unique().tolist()

    st.title(f"{session.event['EventName']} {session.event.year} - {session.name}")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        [
            "Session Overview",
            "Telemetry Deep Dive",
            "Lap Time Analysis",
            "Predictions & Modelling",
            "AI Race Debrief",
            "Live Race Predictor",
            "Energy & Braking",
            "Live Timing (Real-Time)",
        ]
    )

    # -----------------------------------------------------------------------
    # TAB 1 - Session Overview
    # -----------------------------------------------------------------------
    with tab1:
        st.header("Session Overview")

        # Weather summary
        weather = session.weather_data
        if weather is not None and not weather.empty:
            cols = st.columns(4)
            with cols[0]:
                st.markdown(
                    f'<div class="metric-card"><h3>Track Temp</h3><p>{weather["TrackTemp"].mean():.1f} C</p></div>',
                    unsafe_allow_html=True,
                )
            with cols[1]:
                st.markdown(
                    f'<div class="metric-card"><h3>Air Temp</h3><p>{weather["AirTemp"].mean():.1f} C</p></div>',
                    unsafe_allow_html=True,
                )
            with cols[2]:
                rain = weather["Rainfall"].any() if "Rainfall" in weather.columns else False
                st.markdown(
                    f'<div class="metric-card"><h3>Rain</h3><p>{"Yes" if rain else "No"}</p></div>',
                    unsafe_allow_html=True,
                )
            with cols[3]:
                st.markdown(
                    f'<div class="metric-card"><h3>Humidity</h3><p>{weather["Humidity"].mean():.0f}%</p></div>',
                    unsafe_allow_html=True,
                )

        # Results table
        st.subheader("Race Results")
        res_df = results[["Position", "Abbreviation", "TeamName", "Points", "Time", "Status"]].copy()
        res_df.columns = ["Pos", "Driver", "Team", "Points", "Time", "Status"]
        st.dataframe(res_df, use_container_width=True, hide_index=True)

        # Tyre strategy timeline
        st.subheader("Tyre Strategy")
        fig_strat = go.Figure()
        driver_order = (
            results.sort_values("Position")["Abbreviation"].tolist()
        )

        for i, drv in enumerate(driver_order):
            drv_laps = laps[laps["Driver"] == drv].sort_values("LapNumber")
            if drv_laps.empty:
                continue
            stints = drv_laps.groupby(
                (drv_laps["Compound"] != drv_laps["Compound"].shift()).cumsum()
            )
            for _, stint in stints:
                compound = stint["Compound"].iloc[0]
                start_lap = stint["LapNumber"].iloc[0]
                end_lap = stint["LapNumber"].iloc[-1]
                color = COMPOUND_COLORS.get(str(compound).upper(), "#888888")
                fig_strat.add_trace(
                    go.Bar(
                        x=[end_lap - start_lap + 1],
                        y=[drv],
                        base=start_lap - 1,
                        orientation="h",
                        marker_color=color,
                        marker_line_color="#1A1D23",
                        marker_line_width=1,
                        name=str(compound),
                        showlegend=False,
                        hovertemplate=f"{drv}: {compound} (Laps {start_lap}-{end_lap})<extra></extra>",
                    )
                )

        fig_strat.update_layout(
            barmode="stack",
            template="plotly_dark",
            paper_bgcolor="#0E1117",
            plot_bgcolor="#1A1D23",
            height=max(400, len(driver_order) * 22),
            xaxis_title="Lap",
            yaxis=dict(categoryorder="array", categoryarray=list(reversed(driver_order))),
            margin=dict(l=60, r=20, t=20, b=40),
        )
        st.plotly_chart(fig_strat, use_container_width=True)

    # -----------------------------------------------------------------------
    # TAB 2 - Telemetry Deep Dive
    # -----------------------------------------------------------------------
    with tab2:
        st.header("Telemetry Deep Dive")
        col_a, col_b = st.columns(2)
        with col_a:
            drv1 = st.selectbox("Driver 1", drivers, index=0, key="tele_drv1")
        with col_b:
            drv2 = st.selectbox(
                "Driver 2", drivers, index=min(1, len(drivers) - 1), key="tele_drv2"
            )

        def get_fastest_tel(driver):
            drv_laps = laps.pick_drivers(driver).pick_quicklaps()
            if drv_laps.empty:
                drv_laps = laps.pick_drivers(driver)
            fastest = drv_laps.pick_fastest()
            if fastest is None:
                return None, None
            tel = fastest.get_telemetry()
            return fastest, tel

        fl1, tel1 = get_fastest_tel(drv1)
        fl2, tel2 = get_fastest_tel(drv2)

        if tel1 is not None and tel2 is not None:
            fig_tel = make_subplots(
                rows=4,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.04,
                subplot_titles=("Speed (km/h)", "Throttle %", "Brake Pressure", "Delta Time (s)"),
                row_heights=[0.35, 0.2, 0.2, 0.25],
            )

            team1 = results[results["Abbreviation"] == drv1]["TeamName"].values
            team2 = results[results["Abbreviation"] == drv2]["TeamName"].values
            c1 = TEAM_COLORS.get(team1[0], "#FF4444") if len(team1) > 0 else "#FF4444"
            c2 = TEAM_COLORS.get(team2[0], "#4488FF") if len(team2) > 0 else "#4488FF"

            # Speed
            fig_tel.add_trace(go.Scatter(x=tel1["Distance"], y=tel1["Speed"], name=drv1, line=dict(color=c1, width=2)), row=1, col=1)
            fig_tel.add_trace(go.Scatter(x=tel2["Distance"], y=tel2["Speed"], name=drv2, line=dict(color=c2, width=2)), row=1, col=1)

            # Throttle
            fig_tel.add_trace(go.Scatter(x=tel1["Distance"], y=tel1["Throttle"], name=drv1, line=dict(color=c1, width=1.5), showlegend=False), row=2, col=1)
            fig_tel.add_trace(go.Scatter(x=tel2["Distance"], y=tel2["Throttle"], name=drv2, line=dict(color=c2, width=1.5), showlegend=False), row=2, col=1)

            # Brake
            fig_tel.add_trace(go.Scatter(x=tel1["Distance"], y=tel1["Brake"].astype(int), name=drv1, line=dict(color=c1, width=1.5), showlegend=False), row=3, col=1)
            fig_tel.add_trace(go.Scatter(x=tel2["Distance"], y=tel2["Brake"].astype(int), name=drv2, line=dict(color=c2, width=1.5), showlegend=False), row=3, col=1)

            # Delta time
            min_len = min(len(tel1), len(tel2))
            t1 = tel1["Time"].iloc[:min_len].dt.total_seconds().values if hasattr(tel1["Time"].iloc[0], "total_seconds") else tel1["Time"].iloc[:min_len].values / 1e9
            t2 = tel2["Time"].iloc[:min_len].dt.total_seconds().values if hasattr(tel2["Time"].iloc[0], "total_seconds") else tel2["Time"].iloc[:min_len].values / 1e9
            delta = t1 - t2
            dist_delta = tel1["Distance"].iloc[:min_len]
            fig_tel.add_trace(
                go.Scatter(
                    x=dist_delta,
                    y=delta,
                    name=f"Delta ({drv1} - {drv2})",
                    fill="tozeroy",
                    line=dict(color="#FFD700", width=1.5),
                ),
                row=4,
                col=1,
            )

            fig_tel.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0E1117",
                plot_bgcolor="#1A1D23",
                height=900,
                margin=dict(l=60, r=20, t=40, b=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig_tel.update_xaxes(title_text="Distance (m)", row=4, col=1)
            st.plotly_chart(fig_tel, use_container_width=True)
        else:
            st.warning("Telemetry data not available for selected drivers.")

    # -----------------------------------------------------------------------
    # TAB 3 - Lap Time Analysis
    # -----------------------------------------------------------------------
    with tab3:
        st.header("Lap Time Analysis")

        top5 = results.sort_values("Position").head(5)["Abbreviation"].tolist()

        fig_lt = go.Figure()
        pit_laps_all = set()

        for drv in top5:
            drv_laps = laps[laps["Driver"] == drv].copy()
            drv_laps = drv_laps[drv_laps["PitInTime"].isna() & drv_laps["PitOutTime"].isna()]
            drv_laps = drv_laps.dropna(subset=["LapTime"])
            drv_laps["LapTimeSec"] = drv_laps["LapTime"].dt.total_seconds()

            # Filter out outliers (safety car laps, etc.) - beyond 110% of median
            median_time = drv_laps["LapTimeSec"].median()
            if pd.notna(median_time):
                drv_laps = drv_laps[drv_laps["LapTimeSec"] < median_time * 1.10]

            team_row = results[results["Abbreviation"] == drv]["TeamName"].values
            color = TEAM_COLORS.get(team_row[0], "#FFFFFF") if len(team_row) > 0 else "#FFFFFF"

            fig_lt.add_trace(
                go.Scatter(
                    x=drv_laps["LapNumber"],
                    y=drv_laps["LapTimeSec"],
                    name=drv,
                    mode="lines+markers",
                    marker=dict(size=4),
                    line=dict(color=color, width=2),
                )
            )

            # Find pit laps
            all_drv_laps = laps[laps["Driver"] == drv]
            pits = all_drv_laps[all_drv_laps["PitInTime"].notna()]["LapNumber"].tolist()
            pit_laps_all.update(pits)

        # Add pit stop vertical lines
        for plap in sorted(pit_laps_all):
            fig_lt.add_vline(x=plap, line_dash="dot", line_color="#555555", line_width=1)

        fig_lt.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0E1117",
            plot_bgcolor="#1A1D23",
            height=500,
            xaxis_title="Lap",
            yaxis_title="Lap Time (s)",
            margin=dict(l=60, r=20, t=20, b=40),
        )
        st.plotly_chart(fig_lt, use_container_width=True)

        # Tyre degradation model
        st.subheader("Tyre Degradation Model")
        deg_rows = []
        for drv in top5:
            drv_laps = laps[laps["Driver"] == drv].sort_values("LapNumber").copy()
            drv_laps = drv_laps.dropna(subset=["LapTime"])
            drv_laps["LapTimeSec"] = drv_laps["LapTime"].dt.total_seconds()

            stint_groups = drv_laps.groupby(
                (drv_laps["Compound"] != drv_laps["Compound"].shift()).cumsum()
            )
            stint_num = 1
            for _, stint in stint_groups:
                # Filter out pit in/out laps within stint
                clean = stint[stint["PitInTime"].isna() & stint["PitOutTime"].isna()]
                median_t = clean["LapTimeSec"].median()
                if pd.notna(median_t):
                    clean = clean[clean["LapTimeSec"] < median_t * 1.10]

                if len(clean) >= 3:
                    x = np.arange(len(clean))
                    y = clean["LapTimeSec"].values
                    slope, _, r, _, _ = stats.linregress(x, y)
                    deg_rows.append(
                        {
                            "Driver": drv,
                            "Stint": stint_num,
                            "Compound": clean["Compound"].iloc[0],
                            "Laps": len(clean),
                            "Deg (s/lap)": round(slope, 4),
                            "R-squared": round(r**2, 3),
                        }
                    )
                stint_num += 1

        if deg_rows:
            deg_df = pd.DataFrame(deg_rows)
            st.dataframe(deg_df, use_container_width=True, hide_index=True)
        else:
            st.info("Not enough data to compute degradation slopes.")

    # -----------------------------------------------------------------------
    # TAB 4 - Predictions & Modelling
    # -----------------------------------------------------------------------
    with tab4:
        st.header("Predictions & Modelling")

        # --- Tyre Life Predictor ---
        st.subheader("Tyre Life Predictor")
        threshold = st.slider("Deg threshold (s above stint baseline)", 0.5, 3.0, 1.5, 0.1)

        pred_rows = []
        for drv in drivers:
            drv_laps = laps[laps["Driver"] == drv].sort_values("LapNumber").copy()
            drv_laps = drv_laps.dropna(subset=["LapTime"])
            drv_laps["LapTimeSec"] = drv_laps["LapTime"].dt.total_seconds()

            stint_groups = drv_laps.groupby(
                (drv_laps["Compound"] != drv_laps["Compound"].shift()).cumsum()
            )
            for _, stint in stint_groups:
                clean = stint[stint["PitInTime"].isna() & stint["PitOutTime"].isna()]
                median_t = clean["LapTimeSec"].median()
                if pd.notna(median_t):
                    clean = clean[clean["LapTimeSec"] < median_t * 1.10]
                if len(clean) < 3:
                    continue

                x = np.arange(len(clean))
                y = clean["LapTimeSec"].values
                slope, intercept, _, _, _ = stats.linregress(x, y)
                baseline = intercept

                if slope > 0:
                    predicted_life = threshold / slope  # laps until threshold exceeded
                else:
                    predicted_life = 999  # no degradation

                actual_stint_len = len(stint)
                actual_pit_lap = stint["LapNumber"].iloc[-1]
                pitted = stint["PitInTime"].notna().any()

                pred_rows.append(
                    {
                        "Driver": drv,
                        "Compound": clean["Compound"].iloc[0],
                        "Predicted Life (laps)": round(predicted_life, 1),
                        "Actual Stint (laps)": actual_stint_len,
                        "Actual Pit Lap": int(actual_pit_lap) if pitted else "N/A",
                        "Deg (s/lap)": round(slope, 4),
                    }
                )

        if pred_rows:
            pred_df = pd.DataFrame(pred_rows)
            st.dataframe(pred_df, use_container_width=True, hide_index=True)

        # --- Pace-Adjusted Standings ---
        st.subheader("Pace-Adjusted Standings")
        pace_rows = []
        for drv in drivers:
            drv_laps = laps[laps["Driver"] == drv].copy()
            drv_laps = drv_laps.dropna(subset=["LapTime"])
            drv_laps["LapTimeSec"] = drv_laps["LapTime"].dt.total_seconds()
            # Remove in/out laps and SC laps (approximated by >110% of median)
            clean = drv_laps[drv_laps["PitInTime"].isna() & drv_laps["PitOutTime"].isna()]
            median_t = clean["LapTimeSec"].median()
            if pd.notna(median_t) and not clean.empty:
                clean = clean[clean["LapTimeSec"] < median_t * 1.10]
                pace_rows.append(
                    {"Driver": drv, "Median Pace (s)": round(clean["LapTimeSec"].median(), 3)}
                )

        if pace_rows:
            pace_df = pd.DataFrame(pace_rows).sort_values("Median Pace (s)")
            pace_df["Pace Rank"] = range(1, len(pace_df) + 1)

            actual_order = results.sort_values("Position")[["Abbreviation", "Position"]].rename(
                columns={"Abbreviation": "Driver", "Position": "Actual Pos"}
            )
            merged = pace_df.merge(actual_order, on="Driver", how="left")
            merged["Delta"] = merged["Actual Pos"].astype(float) - merged["Pace Rank"]
            st.dataframe(merged, use_container_width=True, hide_index=True)

        # --- Overtake Opportunity Scorer ---
        st.subheader("Overtake Opportunity Scorer (Final 10 Laps)")
        max_lap = int(laps["LapNumber"].max()) if not laps.empty else 0
        final_laps = laps[laps["LapNumber"] > max_lap - 10].copy()

        if not final_laps.empty:
            last_lap = final_laps[final_laps["LapNumber"] == max_lap].sort_values("Position")
            ot_rows = []
            for idx in range(1, len(last_lap)):
                behind = last_lap.iloc[idx]
                ahead = last_lap.iloc[idx - 1]

                gap = 0
                if pd.notna(behind.get("LapTime")) and pd.notna(ahead.get("LapTime")):
                    gap = abs(
                        behind["LapTime"].total_seconds() - ahead["LapTime"].total_seconds()
                    )

                # Tyre age delta
                behind_age = behind.get("TyreLife", 0) or 0
                ahead_age = ahead.get("TyreLife", 0) or 0
                tyre_delta = float(ahead_age) - float(behind_age)

                # Compound advantage
                compound_rank = {"SOFT": 1, "MEDIUM": 2, "HARD": 3}
                behind_comp = compound_rank.get(str(behind.get("Compound", "")).upper(), 2)
                ahead_comp = compound_rank.get(str(ahead.get("Compound", "")).upper(), 2)
                compound_adv = ahead_comp - behind_comp

                # Score: lower gap = higher, positive tyre delta = higher, compound advantage
                gap_score = max(0, 3 - gap) / 3 * 40
                tyre_score = min(max(tyre_delta, -10), 10) / 10 * 30
                comp_score = compound_adv * 15
                total = max(0, gap_score + tyre_score + comp_score)

                ot_rows.append(
                    {
                        "Driver": behind["Driver"],
                        "Attacking": ahead["Driver"],
                        "Gap (s)": round(gap, 3),
                        "Tyre Age Delta": int(tyre_delta),
                        "Score": round(total, 1),
                    }
                )

            if ot_rows:
                ot_df = pd.DataFrame(ot_rows).sort_values("Score", ascending=False)
                fig_ot = go.Figure(
                    go.Bar(
                        y=ot_df["Driver"] + " -> " + ot_df["Attacking"],
                        x=ot_df["Score"],
                        orientation="h",
                        marker_color="#FF8000",
                        text=ot_df["Score"].round(1),
                        textposition="outside",
                    )
                )
                fig_ot.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="#0E1117",
                    plot_bgcolor="#1A1D23",
                    height=max(300, len(ot_df) * 30),
                    xaxis_title="Overtake Score",
                    yaxis=dict(categoryorder="total ascending"),
                    margin=dict(l=100, r=40, t=20, b=40),
                )
                st.plotly_chart(fig_ot, use_container_width=True)
        else:
            st.info("Not enough lap data for overtake analysis.")

    # -----------------------------------------------------------------------
    # TAB 5 - AI Race Debrief
    # -----------------------------------------------------------------------
    with tab5:
        st.header("AI Race Debrief")

        api_key = st.text_input("Anthropic API Key", type="password", key="api_key")

        if st.button("Generate Debrief", type="primary"):
            if not api_key:
                st.warning("Please enter your Anthropic API key.")
            else:
                # Build summary data
                top3 = results.sort_values("Position").head(3)
                top3_list = [
                    {"pos": int(r["Position"]), "driver": r["Abbreviation"], "team": r["TeamName"]}
                    for _, r in top3.iterrows()
                ]

                # Fastest lap
                fl_data = None
                fastest_laps = laps.dropna(subset=["LapTime"])
                if not fastest_laps.empty:
                    fl_row = fastest_laps.loc[fastest_laps["LapTime"].idxmin()]
                    fl_data = {
                        "driver": fl_row["Driver"],
                        "time": str(fl_row["LapTime"]),
                        "lap": int(fl_row["LapNumber"]),
                    }

                # Position changes
                pos_changes = []
                for _, r in results.iterrows():
                    grid = r.get("GridPosition", 0)
                    finish = r.get("Position", 0)
                    if pd.notna(grid) and pd.notna(finish):
                        delta = int(grid) - int(finish)
                        if abs(delta) >= 3:
                            pos_changes.append(
                                {
                                    "driver": r["Abbreviation"],
                                    "grid": int(grid),
                                    "finish": int(finish),
                                    "gained": delta,
                                }
                            )

                # Tyre strategy outliers
                strategy_info = []
                for drv in driver_order[:5]:
                    drv_laps = laps[laps["Driver"] == drv]
                    compounds = drv_laps["Compound"].dropna().unique().tolist()
                    n_stops = drv_laps["PitInTime"].notna().sum()
                    strategy_info.append(
                        {"driver": drv, "stops": int(n_stops), "compounds": compounds}
                    )

                summary = {
                    "event": session.event["EventName"],
                    "year": int(session.event.year),
                    "top3": top3_list,
                    "fastest_lap": fl_data,
                    "position_changes": pos_changes,
                    "strategies": strategy_info,
                }

                prompt = f"""You are an F1 race engineer writing a post-race debrief.

Here is the session data:
{summary}

Write:
1. A 3-paragraph race engineer debrief covering: what happened, key strategy moments, and standout performances.
2. Then 3 bullet points under "Watch for next race" with predictions based on trends.

Keep the tone professional but engaging, like a real race engineer briefing the team."""

                with st.spinner("Generating AI debrief..."):
                    try:
                        client = anthropic.Anthropic(api_key=api_key)
                        message = client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=1024,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        debrief_text = message.content[0].text
                        st.markdown(
                            f'<div class="debrief-card">{debrief_text}</div>',
                            unsafe_allow_html=True,
                        )
                    except Exception as e:
                        st.error(f"API error: {e}")

    # -----------------------------------------------------------------------
    # TAB 6 - Live Race Predictor
    # -----------------------------------------------------------------------
    with tab6:
        st.header("Live Race Predictor")
        st.caption(
            "Replays a completed race lap-by-lap, simulating a live prediction model. "
            "During an actual live race, this same model runs on real-time timing data."
        )

        max_race_lap = int(laps["LapNumber"].max()) if not laps.empty else 0

        current_lap = st.slider(
            "Simulate up to lap", 1, max(1, max_race_lap), max(1, max_race_lap // 2),
            key="live_lap_slider",
        )

        # Auto-play mode
        auto_col1, auto_col2 = st.columns([1, 4])
        with auto_col1:
            auto_play = st.button("Auto-play", key="auto_play_btn")
        with auto_col2:
            st.caption("Steps through 1 lap at a time (click repeatedly or hold)")

        if auto_play and current_lap < max_race_lap:
            st.session_state["live_lap_slider"] = current_lap + 1
            st.rerun()

        # Filter laps to only what's "happened" so far
        live_laps = laps[laps["LapNumber"] <= current_lap].copy()

        if live_laps.empty:
            st.warning("No lap data available yet.")
        else:
            # --- Current standings ---
            latest = live_laps[live_laps["LapNumber"] == current_lap].sort_values("Position")
            if latest.empty:
                latest = live_laps.groupby("Driver").last().sort_values("Position").reset_index()

            st.subheader(f"Race Standings - Lap {current_lap}/{max_race_lap}")

            # --- Win Probability Model ---
            # Factors: current position, recent pace trend, tyre age, gap to leader
            prob_rows = []
            leader_time = None

            for _, row in latest.iterrows():
                drv = row["Driver"]
                pos = row.get("Position", 20)
                if pd.isna(pos):
                    pos = 20

                # Recent pace (last 5 clean laps)
                drv_recent = live_laps[
                    (live_laps["Driver"] == drv)
                    & (live_laps["LapTime"].notna())
                    & (live_laps["PitInTime"].isna())
                    & (live_laps["PitOutTime"].isna())
                ].tail(5)

                if not drv_recent.empty:
                    recent_pace = drv_recent["LapTime"].dt.total_seconds().median()
                else:
                    recent_pace = None

                # Tyre info
                tyre_age = row.get("TyreLife", 0) or 0
                compound = str(row.get("Compound", "MEDIUM")).upper()

                # Cumulative time (approximate gap from race time)
                drv_all = live_laps[live_laps["Driver"] == drv]
                cum_time = drv_all["LapTime"].dropna().dt.total_seconds().sum()

                if leader_time is None:
                    leader_time = cum_time
                gap_to_leader = cum_time - leader_time if leader_time else 0

                prob_rows.append({
                    "Driver": drv,
                    "Position": int(pos),
                    "Recent Pace (s)": round(recent_pace, 3) if recent_pace else None,
                    "Tyre": compound,
                    "Tyre Age": int(tyre_age),
                    "Gap to Leader (s)": round(gap_to_leader, 1),
                    "_pace": recent_pace,
                    "_pos": float(pos),
                    "_tyre_age": float(tyre_age),
                    "_gap": gap_to_leader,
                })

            if prob_rows:
                prob_df = pd.DataFrame(prob_rows)

                # --- Calculate win probability ---
                # Score based on: position (40%), pace (30%), tyre freshness (15%), gap (15%)
                laps_remaining = max_race_lap - current_lap
                race_progress = current_lap / max_race_lap if max_race_lap > 0 else 0

                # Position score: P1=1.0, P20=0.0
                max_pos = prob_df["_pos"].max()
                prob_df["pos_score"] = (max_pos - prob_df["_pos"]) / max(max_pos - 1, 1)

                # Pace score: fastest median = 1.0
                valid_pace = prob_df["_pace"].dropna()
                if not valid_pace.empty:
                    min_pace = valid_pace.min()
                    max_pace = valid_pace.max()
                    spread = max_pace - min_pace if max_pace != min_pace else 1
                    prob_df["pace_score"] = prob_df["_pace"].apply(
                        lambda p: (max_pace - p) / spread if pd.notna(p) else 0
                    )
                else:
                    prob_df["pace_score"] = 0

                # Tyre score: fresher = better, but compound matters
                compound_bonus = {"SOFT": 0.15, "MEDIUM": 0.05, "HARD": -0.05}
                max_age = prob_df["_tyre_age"].max() if prob_df["_tyre_age"].max() > 0 else 1
                prob_df["tyre_score"] = (1 - prob_df["_tyre_age"] / max_age) + prob_df["Tyre"].map(
                    lambda c: compound_bonus.get(c, 0)
                )
                prob_df["tyre_score"] = prob_df["tyre_score"].clip(0, 1)

                # Gap score: smaller gap to leader = better
                max_gap = prob_df["_gap"].max() if prob_df["_gap"].max() > 0 else 1
                prob_df["gap_score"] = 1 - (prob_df["_gap"] / max_gap)

                # Weighted total — position matters more as race progresses
                pos_weight = 0.25 + 0.35 * race_progress  # 25% early -> 60% late
                pace_weight = 0.35 - 0.15 * race_progress  # 35% early -> 20% late
                tyre_weight = 0.20 - 0.05 * race_progress  # 20% early -> 15% late
                gap_weight = 1 - pos_weight - pace_weight - tyre_weight

                prob_df["raw_score"] = (
                    prob_df["pos_score"] * pos_weight
                    + prob_df["pace_score"] * pace_weight
                    + prob_df["tyre_score"] * tyre_weight
                    + prob_df["gap_score"] * gap_weight
                )

                # Softmax to get probabilities
                scores = prob_df["raw_score"].values
                # Temperature: lower = more confident as race progresses
                temp = max(0.3, 1.5 - race_progress * 1.2)
                exp_scores = np.exp((scores - scores.max()) / temp)
                prob_df["Win %"] = (exp_scores / exp_scores.sum() * 100).round(1)

                prob_df = prob_df.sort_values("Win %", ascending=False)

                # --- Display ---
                col_stand, col_chart = st.columns([1, 2])

                with col_stand:
                    display_df = prob_df[
                        ["Driver", "Position", "Recent Pace (s)", "Tyre", "Tyre Age", "Gap to Leader (s)", "Win %"]
                    ].reset_index(drop=True)
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

                with col_chart:
                    top10 = prob_df.head(10)
                    colors = []
                    for drv in top10["Driver"]:
                        team_row = results[results["Abbreviation"] == drv]["TeamName"].values
                        c = TEAM_COLORS.get(team_row[0], "#FFFFFF") if len(team_row) > 0 else "#FFFFFF"
                        colors.append(c)

                    fig_prob = go.Figure(
                        go.Bar(
                            y=top10["Driver"],
                            x=top10["Win %"],
                            orientation="h",
                            marker_color=colors,
                            text=top10["Win %"].apply(lambda x: f"{x:.1f}%"),
                            textposition="outside",
                            textfont=dict(color="#FFFFFF"),
                        )
                    )
                    fig_prob.update_layout(
                        title=f"Win Probability - Lap {current_lap}/{max_race_lap}",
                        template="plotly_dark",
                        paper_bgcolor="#0E1117",
                        plot_bgcolor="#1A1D23",
                        height=400,
                        xaxis_title="Win Probability (%)",
                        yaxis=dict(categoryorder="total ascending"),
                        margin=dict(l=60, r=60, t=40, b=40),
                    )
                    st.plotly_chart(fig_prob, use_container_width=True)

                # --- Position History Chart ---
                st.subheader("Position Battle")
                fig_pos = go.Figure()
                top_drivers = prob_df.head(5)["Driver"].tolist()

                for drv in top_drivers:
                    drv_data = live_laps[live_laps["Driver"] == drv].sort_values("LapNumber")
                    drv_data = drv_data.dropna(subset=["Position"])
                    team_row = results[results["Abbreviation"] == drv]["TeamName"].values
                    c = TEAM_COLORS.get(team_row[0], "#FFFFFF") if len(team_row) > 0 else "#FFFFFF"
                    fig_pos.add_trace(
                        go.Scatter(
                            x=drv_data["LapNumber"],
                            y=drv_data["Position"],
                            name=drv,
                            mode="lines",
                            line=dict(color=c, width=2.5),
                        )
                    )

                fig_pos.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="#0E1117",
                    plot_bgcolor="#1A1D23",
                    height=400,
                    xaxis_title="Lap",
                    yaxis_title="Position",
                    yaxis=dict(autorange="reversed", dtick=1),
                    margin=dict(l=60, r=20, t=20, b=40),
                )
                st.plotly_chart(fig_pos, use_container_width=True)

                # --- Predicted Finish ---
                if laps_remaining > 0 and laps_remaining < max_race_lap:
                    st.subheader("Predicted Final Order")
                    st.caption(
                        f"{laps_remaining} laps remaining - projecting based on pace, "
                        "tyre deg, and current gaps"
                    )

                    finish_rows = []
                    for _, row in prob_df.iterrows():
                        drv = row["Driver"]
                        pace = row["_pace"]
                        tyre_age = row["_tyre_age"]
                        gap = row["_gap"]

                        if pace is None:
                            projected_gap = gap
                        else:
                            # Estimate deg from recent laps
                            drv_recent = live_laps[
                                (live_laps["Driver"] == drv)
                                & (live_laps["LapTime"].notna())
                                & (live_laps["PitInTime"].isna())
                            ].tail(10)
                            if len(drv_recent) >= 3:
                                x = np.arange(len(drv_recent))
                                y = drv_recent["LapTime"].dt.total_seconds().values
                                deg_slope, _, _, _, _ = stats.linregress(x, y)
                            else:
                                deg_slope = 0.02  # default assumption

                            # Project cumulative time over remaining laps
                            projected_time = sum(
                                pace + deg_slope * i for i in range(laps_remaining)
                            )
                            # Compare to leader's projection
                            leader_pace = prob_df.iloc[0]["_pace"] or pace
                            leader_projected = leader_pace * laps_remaining
                            projected_gap = gap + (projected_time - leader_projected)

                        finish_rows.append({
                            "Driver": drv,
                            "Current Pos": int(row["Position"]),
                            "Projected Gap (s)": round(projected_gap, 1),
                        })

                    finish_df = pd.DataFrame(finish_rows).sort_values("Projected Gap (s)")
                    finish_df["Predicted Pos"] = range(1, len(finish_df) + 1)
                    finish_df["Change"] = finish_df["Current Pos"] - finish_df["Predicted Pos"]
                    finish_df["Change"] = finish_df["Change"].apply(
                        lambda x: f"+{x}" if x > 0 else str(x) if x < 0 else "-"
                    )
                    st.dataframe(
                        finish_df[["Predicted Pos", "Driver", "Current Pos", "Projected Gap (s)", "Change"]],
                        use_container_width=True,
                        hide_index=True,
                    )

    # -----------------------------------------------------------------------
    # TAB 7 - Energy & Braking Analysis
    # -----------------------------------------------------------------------
    with tab7:
        st.header("Energy & Braking Analysis")
        st.caption(
            "Detects braking zones, coasting/harvesting zones, throttle lift points, "
            "and trail braking — critical for 2026 energy management regs."
        )

        drv_energy = st.selectbox("Driver", drivers, index=0, key="energy_drv")

        # Get fastest lap telemetry
        drv_laps_e = laps.pick_drivers(drv_energy).pick_quicklaps()
        if drv_laps_e.empty:
            drv_laps_e = laps.pick_drivers(drv_energy)
        fastest_e = drv_laps_e.pick_fastest()

        if fastest_e is not None:
            tel_e = fastest_e.get_telemetry()

            if not tel_e.empty:
                tel_e = tel_e.copy()
                dist = tel_e["Distance"].values
                speed = tel_e["Speed"].values
                throttle = tel_e["Throttle"].values
                brake = tel_e["Brake"].values.astype(float)
                gear = tel_e["nGear"].values if "nGear" in tel_e.columns else None

                # --- Classify each telemetry point ---
                zones = []
                for i in range(len(tel_e)):
                    thr = throttle[i]
                    brk = brake[i]
                    if brk > 0 and thr > 10:
                        zones.append("Trail Brake")
                    elif brk > 0:
                        zones.append("Full Brake")
                    elif thr < 5:
                        zones.append("Coast/Harvest")
                    elif thr < 80:
                        zones.append("Partial Throttle")
                    else:
                        zones.append("Full Throttle")

                tel_e["Zone"] = zones

                zone_colors = {
                    "Full Throttle": "#00CC00",
                    "Partial Throttle": "#88CC44",
                    "Coast/Harvest": "#FFD700",
                    "Full Brake": "#FF3333",
                    "Trail Brake": "#FF8800",
                }

                # --- Speed trace colored by zone ---
                st.subheader("Speed Trace by Driving Zone")
                fig_zone = go.Figure()

                for zone_name, color in zone_colors.items():
                    mask = tel_e["Zone"] == zone_name
                    if mask.any():
                        fig_zone.add_trace(
                            go.Scatter(
                                x=tel_e.loc[mask, "Distance"],
                                y=tel_e.loc[mask, "Speed"],
                                mode="markers",
                                marker=dict(color=color, size=3),
                                name=zone_name,
                            )
                        )

                fig_zone.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="#0E1117",
                    plot_bgcolor="#1A1D23",
                    height=400,
                    xaxis_title="Distance (m)",
                    yaxis_title="Speed (km/h)",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    margin=dict(l=60, r=20, t=40, b=40),
                )
                st.plotly_chart(fig_zone, use_container_width=True)

                # --- Detailed Throttle/Brake/Speed overlay ---
                st.subheader("Throttle, Brake & Speed Detail")
                fig_detail = make_subplots(
                    rows=3, cols=1, shared_xaxes=True,
                    vertical_spacing=0.04,
                    subplot_titles=("Speed (km/h)", "Throttle %", "Brake"),
                    row_heights=[0.4, 0.3, 0.3],
                )

                team_row_e = results[results["Abbreviation"] == drv_energy]["TeamName"].values
                drv_color = TEAM_COLORS.get(team_row_e[0], "#FFFFFF") if len(team_row_e) > 0 else "#FFFFFF"

                fig_detail.add_trace(
                    go.Scatter(x=dist, y=speed, line=dict(color=drv_color, width=2), name="Speed", showlegend=False),
                    row=1, col=1,
                )
                fig_detail.add_trace(
                    go.Scatter(x=dist, y=throttle, line=dict(color="#00CC00", width=1.5), name="Throttle", fill="tozeroy", fillcolor="rgba(0,204,0,0.15)", showlegend=False),
                    row=2, col=1,
                )
                fig_detail.add_trace(
                    go.Scatter(x=dist, y=brake, line=dict(color="#FF3333", width=1.5), name="Brake", fill="tozeroy", fillcolor="rgba(255,51,51,0.15)", showlegend=False),
                    row=3, col=1,
                )

                # Shade coasting zones on the speed trace
                coast_mask = tel_e["Zone"] == "Coast/Harvest"
                if coast_mask.any():
                    # Find contiguous coasting regions
                    coast_starts = []
                    coast_ends = []
                    in_coast = False
                    for i in range(len(coast_mask)):
                        if coast_mask.iloc[i] and not in_coast:
                            coast_starts.append(dist[i])
                            in_coast = True
                        elif not coast_mask.iloc[i] and in_coast:
                            coast_ends.append(dist[i])
                            in_coast = False
                    if in_coast:
                        coast_ends.append(dist[-1])

                    for s, e in zip(coast_starts, coast_ends):
                        for row_idx in range(1, 4):
                            fig_detail.add_vrect(
                                x0=s, x1=e, fillcolor="rgba(255,215,0,0.08)",
                                line_width=0, row=row_idx, col=1,
                            )

                fig_detail.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="#0E1117",
                    plot_bgcolor="#1A1D23",
                    height=700,
                    margin=dict(l=60, r=20, t=40, b=40),
                )
                fig_detail.update_xaxes(title_text="Distance (m)", row=3, col=1)
                st.plotly_chart(fig_detail, use_container_width=True)

                # --- Detected Events Table ---
                st.subheader("Detected Driving Events")

                events = []
                prev_zone = zones[0]
                event_start_dist = dist[0]
                event_start_speed = speed[0]

                for i in range(1, len(zones)):
                    if zones[i] != prev_zone:
                        # Record the completed zone
                        duration_m = dist[i] - event_start_dist
                        if duration_m > 10:  # ignore very short blips
                            speed_change = speed[i] - event_start_speed
                            events.append({
                                "Distance (m)": int(event_start_dist),
                                "Zone": prev_zone,
                                "Length (m)": int(duration_m),
                                "Entry Speed": int(event_start_speed),
                                "Exit Speed": int(speed[i]),
                                "Speed Delta": f"{speed_change:+.0f} km/h",
                            })
                        event_start_dist = dist[i]
                        event_start_speed = speed[i]
                        prev_zone = zones[i]

                if events:
                    events_df = pd.DataFrame(events)
                    st.dataframe(events_df, use_container_width=True, hide_index=True)

                    # --- Zone Summary ---
                    st.subheader("Zone Summary")
                    zone_summary = events_df.groupby("Zone").agg(
                        Count=("Zone", "size"),
                        Total_Distance=("Length (m)", "sum"),
                        Avg_Length=("Length (m)", "mean"),
                    ).reset_index()
                    zone_summary.columns = ["Zone", "Count", "Total Distance (m)", "Avg Length (m)"]
                    zone_summary["Avg Length (m)"] = zone_summary["Avg Length (m)"].round(0).astype(int)

                    total_dist = dist[-1] - dist[0]
                    zone_summary["% of Lap"] = (zone_summary["Total Distance (m)"] / total_dist * 100).round(1)
                    zone_summary = zone_summary.sort_values("Total Distance (m)", ascending=False)
                    st.dataframe(zone_summary, use_container_width=True, hide_index=True)

                    # Zone breakdown pie chart
                    fig_pie = go.Figure(
                        go.Pie(
                            labels=zone_summary["Zone"],
                            values=zone_summary["Total Distance (m)"],
                            marker=dict(colors=[zone_colors.get(z, "#888") for z in zone_summary["Zone"]]),
                            hole=0.4,
                            textinfo="label+percent",
                        )
                    )
                    fig_pie.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="#0E1117",
                        height=350,
                        margin=dict(l=20, r=20, t=20, b=20),
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)

                # --- Gear Map (if gear data available) ---
                if gear is not None:
                    st.subheader("Gear Usage Along Lap")
                    fig_gear = go.Figure()
                    fig_gear.add_trace(
                        go.Scatter(
                            x=dist,
                            y=gear,
                            mode="lines",
                            line=dict(color="#BB86FC", width=2),
                            name="Gear",
                        )
                    )
                    fig_gear.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="#0E1117",
                        plot_bgcolor="#1A1D23",
                        height=250,
                        xaxis_title="Distance (m)",
                        yaxis_title="Gear",
                        yaxis=dict(dtick=1),
                        margin=dict(l=60, r=20, t=20, b=40),
                    )
                    st.plotly_chart(fig_gear, use_container_width=True)
        else:
            st.warning("No telemetry data available for this driver.")

    # -----------------------------------------------------------------------
    # TAB 8 - Live Timing (Real-Time)
    # -----------------------------------------------------------------------
    with tab8:
        st.header("Live Timing (Real-Time)")
        st.markdown(
            """
            Connect to F1's **live timing WebSocket** during an active session.
            This records data in real-time and updates predictions as laps complete.

            **How it works:**
            1. Click **Start Recording** when a session is live on F1TV
            2. The app connects to F1's SignalR timing stream
            3. Lap times, positions, gaps, and tyre data stream in live
            4. Predictions update automatically every few seconds
            """
        )

        LIVE_DATA_FILE = CACHE_DIR / "live_timing.txt"

        # --- Recording controls ---
        rec_col1, rec_col2, rec_col3 = st.columns(3)
        with rec_col1:
            start_rec = st.button("Start Recording", type="primary", key="start_live")
        with rec_col2:
            stop_rec = st.button("Stop Recording", key="stop_live")
        with rec_col3:
            refresh = st.button("Refresh Data", key="refresh_live")

        if start_rec:
            if "live_thread" not in st.session_state or not st.session_state.get("live_running"):
                st.session_state["live_running"] = True

                def record_live():
                    try:
                        client = SignalRClient(
                            filename=str(LIVE_DATA_FILE),
                            filemode="a",
                            timeout=0,
                        )
                        client.start()
                    except Exception as e:
                        st.session_state["live_error"] = str(e)
                    finally:
                        st.session_state["live_running"] = False

                thread = threading.Thread(target=record_live, daemon=True)
                thread.start()
                st.session_state["live_thread"] = thread
                st.success("Recording started! Data streaming from F1 live timing.")
            else:
                st.info("Already recording.")

        if stop_rec:
            st.session_state["live_running"] = False
            st.info("Recording will stop after the current timeout cycle.")

        if st.session_state.get("live_error"):
            st.error(f"Live timing error: {st.session_state['live_error']}")
            st.caption(
                "This usually means no F1 session is currently live. "
                "The WebSocket only works during active F1 sessions (FP, Quali, Race)."
            )
            st.session_state["live_error"] = None

        # --- Status indicator ---
        is_recording = st.session_state.get("live_running", False)
        if is_recording:
            st.markdown(
                '<div class="metric-card"><h3>Status</h3>'
                '<p style="color: #FF3333;">RECORDING LIVE</p></div>',
                unsafe_allow_html=True,
            )

        # --- Parse and display live data ---
        if LIVE_DATA_FILE.exists() and LIVE_DATA_FILE.stat().st_size > 0:
            st.subheader("Live Data Stream")

            lines = LIVE_DATA_FILE.read_text().strip().split("\n")
            st.caption(f"{len(lines)} data points received")

            # Parse timing data
            timing_entries = []
            position_data = []
            latest_weather = {}

            for line in lines:
                try:
                    entry = json.loads(line) if line.startswith("[") else None
                    if entry is None:
                        continue
                    category = entry[0] if len(entry) > 0 else ""

                    if category == "TimingData" and len(entry) > 1:
                        data = entry[1]
                        ts = entry[2] if len(entry) > 2 else ""
                        if "Lines" in data:
                            for drv_num, drv_data in data["Lines"].items():
                                row = {"DriverNumber": drv_num, "Timestamp": ts}
                                if "LastLapTime" in drv_data:
                                    lt = drv_data["LastLapTime"]
                                    if isinstance(lt, dict):
                                        row["LapTime"] = lt.get("Value", "")
                                    else:
                                        row["LapTime"] = lt
                                if "GapToLeader" in drv_data:
                                    row["Gap"] = drv_data["GapToLeader"]
                                if "Position" in drv_data:
                                    row["Position"] = drv_data["Position"]
                                if "NumberOfLaps" in drv_data:
                                    row["Laps"] = drv_data["NumberOfLaps"]
                                timing_entries.append(row)

                    elif category == "WeatherData" and len(entry) > 1:
                        latest_weather = entry[1]

                except (json.JSONDecodeError, IndexError, TypeError):
                    continue

            # Display weather if available
            if latest_weather:
                w_cols = st.columns(4)
                with w_cols[0]:
                    st.markdown(
                        f'<div class="metric-card"><h3>Track Temp</h3>'
                        f'<p>{latest_weather.get("TrackTemp", "N/A")} C</p></div>',
                        unsafe_allow_html=True,
                    )
                with w_cols[1]:
                    st.markdown(
                        f'<div class="metric-card"><h3>Air Temp</h3>'
                        f'<p>{latest_weather.get("AirTemp", "N/A")} C</p></div>',
                        unsafe_allow_html=True,
                    )
                with w_cols[2]:
                    rain = latest_weather.get("Rainfall", "0")
                    st.markdown(
                        f'<div class="metric-card"><h3>Rain</h3>'
                        f'<p>{"Yes" if rain not in ("0", "False", False, 0) else "No"}</p></div>',
                        unsafe_allow_html=True,
                    )
                with w_cols[3]:
                    st.markdown(
                        f'<div class="metric-card"><h3>Humidity</h3>'
                        f'<p>{latest_weather.get("Humidity", "N/A")}%</p></div>',
                        unsafe_allow_html=True,
                    )

            # Display timing data
            if timing_entries:
                live_df = pd.DataFrame(timing_entries)

                # Get latest entry per driver
                if "Position" in live_df.columns:
                    latest_per_drv = live_df.groupby("DriverNumber").last().reset_index()
                    latest_per_drv = latest_per_drv.sort_values(
                        "Position", key=lambda x: pd.to_numeric(x, errors="coerce")
                    )

                    display_cols = [c for c in ["Position", "DriverNumber", "LapTime", "Gap", "Laps"] if c in latest_per_drv.columns]
                    st.dataframe(latest_per_drv[display_cols], use_container_width=True, hide_index=True)

                    # Simple live win prediction based on position and gap
                    if "Gap" in latest_per_drv.columns and len(latest_per_drv) > 1:
                        st.subheader("Live Win Probability")
                        live_probs = []
                        for _, row in latest_per_drv.iterrows():
                            pos = pd.to_numeric(row.get("Position", 20), errors="coerce")
                            if pd.isna(pos):
                                pos = 20
                            gap_str = str(row.get("Gap", "0"))
                            try:
                                gap_val = float(gap_str.replace("+", "").replace("LAP", "60").strip() or "0")
                            except ValueError:
                                gap_val = 30
                            live_probs.append({"DriverNumber": row["DriverNumber"], "_pos": pos, "_gap": gap_val})

                        lp_df = pd.DataFrame(live_probs)
                        max_p = lp_df["_pos"].max()
                        lp_df["score"] = (max_p - lp_df["_pos"]) / max(max_p - 1, 1)
                        max_g = lp_df["_gap"].max() if lp_df["_gap"].max() > 0 else 1
                        lp_df["score"] += (1 - lp_df["_gap"] / max_g) * 0.5
                        exp_s = np.exp((lp_df["score"].values - lp_df["score"].max()) / 0.5)
                        lp_df["Win %"] = (exp_s / exp_s.sum() * 100).round(1)
                        lp_df = lp_df.sort_values("Win %", ascending=False)

                        fig_live = go.Figure(
                            go.Bar(
                                y=lp_df["DriverNumber"].head(10),
                                x=lp_df["Win %"].head(10),
                                orientation="h",
                                marker_color="#FF3333",
                                text=lp_df["Win %"].head(10).apply(lambda x: f"{x:.1f}%"),
                                textposition="outside",
                                textfont=dict(color="#FFFFFF"),
                            )
                        )
                        fig_live.update_layout(
                            template="plotly_dark",
                            paper_bgcolor="#0E1117",
                            plot_bgcolor="#1A1D23",
                            height=350,
                            xaxis_title="Win Probability (%)",
                            yaxis=dict(categoryorder="total ascending"),
                            margin=dict(l=60, r=60, t=20, b=40),
                        )
                        st.plotly_chart(fig_live, use_container_width=True)

                st.caption("Click **Refresh Data** to update with latest timing.")
            else:
                st.info("No timing data parsed yet. Data will appear once the session produces lap times.")

        elif not is_recording:
            st.info(
                "No live data available. Click **Start Recording** during an active F1 session.\n\n"
                "**Alternatively**, you can record from terminal:\n"
                "```\n"
                "python -m fastf1.livetiming save live_timing.txt\n"
                "```\n"
                "Then copy the file to `cache/live_timing.txt` and click **Refresh Data**."
            )

else:
    st.title("F1 Race Engineer Dashboard")
    st.info("Select a year, Grand Prix, and session type in the sidebar, then click **Load Session**.")
