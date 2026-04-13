"""
SPEC Scan Viewer - Interactive beamline scan data browser.

Launch:  streamlit run app.py
"""

import base64
import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from spec_parser import parse_spec_file

st.set_page_config(page_title="Alignment Plotter", layout="wide")

# ── Chrome cleanup (hide Deploy + status widget) ─────────────────────────────
st.markdown(
    """
    <style>
    .stDeployButton {display: none;}
    [data-testid="stStatusWidget"] {display: none;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Theme state + runtime dark/light toggle ──────────────────────────────────
if "themes" not in st.session_state:
    st.session_state.themes = {
        "current_theme": "dark",
        "refreshed": True,
        "light": {
            "theme.base": "light",
            "theme.backgroundColor": "#f9f6ef",
            "theme.secondaryBackgroundColor": "#ffffff",
            "theme.primaryColor": "#8B1538",
            "theme.textColor": "#1a1a1a",
            "button_face": "🌙",
        },
        "dark": {
            "theme.base": "dark",
            "theme.backgroundColor": "#1a1a1a",
            "theme.secondaryBackgroundColor": "#2d2d2d",
            "theme.primaryColor": "#8B1538",
            "theme.textColor": "#f0f0f0",
            "button_face": "☀️",
        },
    }


def change_theme():
    current = st.session_state.themes["current_theme"]
    new_theme = "light" if current == "dark" else "dark"
    for key, val in st.session_state.themes[new_theme].items():
        if key.startswith("theme"):
            st._config.set_option(key, val)
    st.session_state.themes["current_theme"] = new_theme
    st.session_state.themes["refreshed"] = False


def apply_current_theme():
    current = st.session_state.themes["current_theme"]
    for key, val in st.session_state.themes[current].items():
        if key.startswith("theme"):
            st._config.set_option(key, val)


apply_current_theme()


def get_logo_base64():
    logo_path = Path(__file__).parent / "ssrl-logo.png"
    if logo_path.exists():
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None


# ── Sidebar header: logo + theme toggle ──────────────────────────────────────
with st.sidebar:
    logo_b64 = get_logo_base64()
    header_left, header_right = st.columns([3, 1])
    with header_left:
        if logo_b64:
            st.markdown(
                f'<img src="data:image/png;base64,{logo_b64}" style="height: 40px;">',
                unsafe_allow_html=True,
            )
    with header_right:
        btn_face = st.session_state.themes[
            st.session_state.themes["current_theme"]
        ]["button_face"]
        st.button(btn_face, on_click=change_theme, help="Toggle light/dark mode")

# After theme change: force one extra rerun so widgets repaint with the new theme
if not st.session_state.themes["refreshed"]:
    st.session_state.themes["refreshed"] = True
    st.rerun()

st.title("Alignment Plotter")


def load_spec_file(filepath):
    return parse_spec_file(filepath)


# ── Sidebar: Data Source ─────────────────────────────────────────────────────
with st.sidebar:
    st.header("Data Source")
    file_path = st.text_input(
        "SPEC data file path", placeholder="/path/to/specfile"
    )

    if not file_path:
        st.info("Enter a path to a SPEC data file to begin.")
        st.stop()

    file_path = os.path.expanduser(file_path)

    if not os.path.isfile(file_path):
        st.error(f"File not found: {file_path}")
        st.stop()

    try:
        spec_file = load_spec_file(file_path)
    except Exception as e:
        st.error(f"Error parsing file: {e}")
        st.stop()

    if not spec_file.scans:
        st.error("No scans found in file.")
        st.stop()

    scan_numbers = sorted(spec_file.scans.keys())
    st.success(
        f"Loaded **{len(scan_numbers)}** scans "
        f"(#{scan_numbers[0]} – #{scan_numbers[-1]})"
    )

# ── Sidebar: Scan Range ─────────────────────────────────────────────────────
with st.sidebar:
    st.header("Scan Range")
    c1, c2 = st.columns(2)
    with c1:
        start_scan = st.number_input(
            "Start", min_value=scan_numbers[0],
            max_value=scan_numbers[-1], value=scan_numbers[0],
        )
    with c2:
        end_scan = st.number_input(
            "End", min_value=scan_numbers[0],
            max_value=scan_numbers[-1], value=scan_numbers[-1],
        )

# ── Sidebar: Motor Filter ───────────────────────────────────────────────────
with st.sidebar:
    st.header("Motor Filter")
    all_scanned_motors = set()
    for s in spec_file.scans.values():
        all_scanned_motors.update(m for m in s.scanned_motors if m)

    motor_options = ["All", "mono + energy"] + sorted(all_scanned_motors)
    default_motor_idx = motor_options.index("mono") if "mono" in motor_options else 0
    motor_filter = st.selectbox("Scan motor", motor_options, index=default_motor_idx)

# ── Sidebar: Options ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Options")
    only_complete = st.checkbox("Only complete scans", value=True)
    normalize = st.checkbox("Normalize each scan (0 → 1)", value=False)


# ── Apply range + motor + completeness filters ──────────────────────────────
def _motor_match(scan, filt):
    if filt == "All":
        return True
    if filt == "mono + energy":
        return any(m in ("mono", "energy") for m in scan.scanned_motors)
    return filt in scan.scanned_motors


preliminary = []
for num in scan_numbers:
    if num < start_scan or num > end_scan:
        continue
    scan = spec_file.scans[num]
    if not _motor_match(scan, motor_filter):
        continue
    if only_complete and not scan.is_complete:
        continue
    if scan.actual_points == 0:
        continue
    preliminary.append(scan)

if not preliminary:
    st.warning("No scans match the current filters.")
    st.stop()


# ── Sidebar: Axis selectors (depend on matching scans) ──────────────────────
all_columns = set()
for s in preliminary:
    all_columns.update(s.column_labels)
all_columns_sorted = sorted(all_columns)

with st.sidebar:
    st.header("Axes")

    # X axis
    x_options = ["Auto (scanned motor)"] + all_columns_sorted
    x_choice = st.selectbox("X axis", x_options)

    # Y axis – smart default
    y_prefs = ["vortDT", "I0", "I1"]
    y_default = next((c for c in y_prefs if c in all_columns), all_columns_sorted[0])
    y_idx = all_columns_sorted.index(y_default)
    y_column = st.selectbox("Y axis", all_columns_sorted, index=y_idx)


# ── Scan selection table ────────────────────────────────────────────────────
st.subheader(f"Matching Scans  ({len(preliminary)})")

rows = []
for s in preliminary:
    pts_str = str(s.actual_points)
    if s.expected_points is not None:
        pts_str += f" / {s.expected_points}"
    rows.append({
        "Plot": True,
        "Scan": s.scan_number,
        "Command": s.command,
        "Pts": pts_str,
        "Date": s.date,
    })

scan_df = pd.DataFrame(rows)

# Key encodes filters so checkboxes reset when filters change
table_key = f"tbl_{start_scan}_{end_scan}_{motor_filter}_{only_complete}"

edited_df = st.data_editor(
    scan_df,
    key=table_key,
    hide_index=True,
    use_container_width=True,
    height=min(400, 35 * len(rows) + 38),
    column_config={
        "Plot": st.column_config.CheckboxColumn(width="small"),
        "Scan": st.column_config.NumberColumn(width="small"),
        "Command": st.column_config.TextColumn(width="large"),
        "Pts": st.column_config.TextColumn(width="small"),
        "Date": st.column_config.TextColumn(width="medium"),
    },
    disabled=["Scan", "Command", "Pts", "Date"],
)

selected_nums = set(edited_df.loc[edited_df["Plot"], "Scan"].tolist())
scans_to_plot = [s for s in preliminary if s.scan_number in selected_nums]

if not scans_to_plot:
    st.info("No scans selected for plotting. Check some boxes above.")
    st.stop()


# ── Plot ─────────────────────────────────────────────────────────────────────
fig = go.Figure()

# Collect per-scan statistics (on raw data, before normalization)
scan_stats = []  # list of dicts: scan_number, x_label, peak_x, peak_y, centroid, fwhm_est

for scan in scans_to_plot:
    # Resolve X column
    if x_choice == "Auto (scanned motor)":
        x_label = scan.column_labels[0] if scan.column_labels else None
    else:
        x_label = x_choice

    if not x_label or x_label not in scan.column_labels:
        continue
    if y_column not in scan.column_labels:
        continue

    xi = scan.column_labels.index(x_label)
    yi = scan.column_labels.index(y_column)

    if xi >= scan.data.shape[1] or yi >= scan.data.shape[1]:
        continue

    x = scan.data[:, xi]
    y_raw = scan.data[:, yi]

    # ── Compute statistics on raw data ──
    if y_raw.size > 0:
        peak_idx = int(np.argmax(y_raw))
        peak_x = float(x[peak_idx])
        peak_y = float(y_raw[peak_idx])

        # Centroid (center of mass) — shift baseline to min so negative regions don't skew
        y_shifted = y_raw - y_raw.min()
        total = y_shifted.sum()
        centroid = float(np.sum(x * y_shifted) / total) if total > 0 else peak_x

        # FWHM estimate — find half-max crossings on the baseline-shifted data
        half_max = y_shifted.max() / 2.0
        above = y_shifted >= half_max
        if above.any():
            indices = np.where(above)[0]
            x_lo = float(x[indices[0]])
            x_hi = float(x[indices[-1]])
            fwhm_est = x_hi - x_lo
        else:
            fwhm_est = np.nan

        scan_stats.append({
            "scan_number": scan.scan_number,
            "x_label": x_label,
            "peak_x": peak_x,
            "peak_y": peak_y,
            "centroid": centroid,
            "fwhm": fwhm_est,
        })

    # ── Plot trace (possibly normalized) ──
    y = y_raw.copy()
    if normalize and y.size > 0:
        ymin, ymax = y.min(), y.max()
        if ymax > ymin:
            y = (y - ymin) / (ymax - ymin)

    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode="lines+markers",
        name=f"#{scan.scan_number}",
        hovertemplate=(
            f"<b>#{scan.scan_number}</b>  {scan.command}<br>"
            "%{x:.4f},  %{y:.4f}<extra></extra>"
        ),
        marker=dict(size=3),
    ))

# Axis labels
if x_choice == "Auto (scanned motor)":
    x_title = scans_to_plot[0].column_labels[0] if scans_to_plot[0].column_labels else "X"
else:
    x_title = x_choice

y_title = y_column + ("  (normalized)" if normalize else "")

fig.update_layout(
    xaxis_title=x_title,
    yaxis_title=y_title,
    height=600,
    hovermode="closest",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)

st.plotly_chart(fig, use_container_width=True)


# ── Motor Position Changes (bonus section) ───────────────────────────────────
st.divider()
with st.expander("Motor Position Changes Between Scans"):
    if len(scans_to_plot) < 2:
        st.info("Select at least 2 scans to compare motor positions.")
    else:
        threshold = st.number_input(
            "Change threshold (absolute)",
            value=0.001, format="%.4f",
            help="Only show motors whose position changed by more than this.",
        )

        any_diffs = False
        for i in range(1, len(scans_to_plot)):
            prev = scans_to_plot[i - 1]
            curr = scans_to_plot[i]
            all_motors = sorted(
                set(prev.motor_positions) | set(curr.motor_positions)
            )
            diffs = []
            for motor in all_motors:
                pv = prev.motor_positions.get(motor)
                cv = curr.motor_positions.get(motor)
                if pv is not None and cv is not None:
                    delta = cv - pv
                    if abs(delta) > threshold:
                        diffs.append({
                            "Motor": motor,
                            f"#{prev.scan_number}": f"{pv:.6g}",
                            f"#{curr.scan_number}": f"{cv:.6g}",
                            "Delta": f"{delta:+.6g}",
                        })
            if diffs:
                any_diffs = True
                st.markdown(f"**#{prev.scan_number} &rarr; #{curr.scan_number}**")
                st.dataframe(
                    pd.DataFrame(diffs), hide_index=True, use_container_width=True
                )

        if not any_diffs:
            st.info("No motor positions changed above the threshold between consecutive scans.")


# ── Scan Statistics (bonus section) ──────────────────────────────────────────
with st.expander("Scan Statistics", expanded=False):
    if not scan_stats:
        st.info("No statistics available (no plottable scans).")
    else:
        stats_df = pd.DataFrame(scan_stats)
        x_unit = stats_df["x_label"].iloc[0]
        scan_labels = [f"#{n}" for n in stats_df["scan_number"]]

        # Summary table
        st.markdown("**Per-scan summary** (computed on raw data)")
        display_df = pd.DataFrame({
            "Scan #": stats_df["scan_number"],
            f"Peak Position ({x_unit})": stats_df["peak_x"].map("{:.4f}".format),
            f"Peak Height ({y_column})": stats_df["peak_y"].map("{:.4f}".format),
            f"Centroid ({x_unit})": stats_df["centroid"].map("{:.4f}".format),
            "FWHM (est.)": stats_df["fwhm"].map(
                lambda v: f"{v:.4f}" if not np.isnan(v) else "—"
            ),
        })
        st.dataframe(display_df, hide_index=True, use_container_width=True)

        # ── Metric definitions for the bar + trend plots ──
        metrics = [
            {
                "key": "peak_x",
                "title": "Peak Position",
                "unit": x_unit,
                "color": "#636EFA",
            },
            {
                "key": "peak_y",
                "title": "Peak Height",
                "unit": y_column,
                "color": "#EF553B",
            },
            {
                "key": "centroid",
                "title": "Centroid",
                "unit": x_unit,
                "color": "#00CC96",
            },
            {
                "key": "fwhm",
                "title": "FWHM (est.)",
                "unit": x_unit,
                "color": "#AB63FA",
            },
        ]

        for metric in metrics:
            vals = stats_df[metric["key"]]
            valid = vals.dropna()
            if valid.empty:
                continue

            st.markdown(f"#### {metric['title']}")
            col_hist, col_trend = st.columns(2)

            # Histogram: distribution of this metric across scans
            with col_hist:
                # Pick bin count: Sturges' rule as a floor, cap at 30
                n = len(valid)
                nbins = max(5, min(30, int(np.ceil(np.log2(n)) + 1)))
                # If the data range is tiny (all values nearly equal),
                # use fewer bins so it doesn't look bizarre
                span = valid.max() - valid.min()
                if span == 0:
                    nbins = 1

                fig_hist = go.Figure()
                fig_hist.add_trace(go.Histogram(
                    x=valid,
                    nbinsx=nbins,
                    marker_color=metric["color"],
                    hovertemplate="%{x:.4f}<br>count: %{y}<extra></extra>",
                ))
                fig_hist.update_layout(
                    title=f"{metric['title']} Distribution",
                    xaxis_title=f"{metric['title']} ({metric['unit']})",
                    yaxis_title="Count",
                    height=300,
                    showlegend=False,
                    bargap=0.05,
                    margin=dict(t=40, b=40),
                )
                st.plotly_chart(fig_hist, use_container_width=True)

            # Trend line: value vs scan number
            with col_trend:
                fig_trend = go.Figure()
                fig_trend.add_trace(go.Scatter(
                    x=stats_df["scan_number"],
                    y=vals,
                    mode="lines+markers",
                    marker=dict(size=7, color=metric["color"]),
                    hovertemplate="Scan #%{x}<br>%{y:.4f}<extra></extra>",
                ))
                fig_trend.update_layout(
                    title=f"{metric['title']} vs Scan #",
                    xaxis_title="Scan #",
                    yaxis_title=f"{metric['title']} ({metric['unit']})",
                    height=300,
                    showlegend=False,
                    margin=dict(t=40, b=40),
                )
                st.plotly_chart(fig_trend, use_container_width=True)
