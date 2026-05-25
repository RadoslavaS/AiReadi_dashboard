"""
AIREADI v3 Dashboard Visualizations
"""
from __future__ import annotations
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from datetime import datetime, timedelta, time
import logging

from config import DATA_ROOT, OUTPUT_ROOT, setup_logging

log = setup_logging("visualizations")

STAGE_COLORS = {
    "awake": "#FFC0CB", "wake":  "#FFC0CB",
    "light": "#ADD8E6", "deep":  "#00008B", "rem":   "#800080",
}

def plot_multimodal(
    participant: str,
    start_dt: datetime,
    end_dt: datetime,
    modalities: list[str],
    split_hour: int = 12,
    loaded_data: dict | None = None,
    return_fig: bool = True
) -> go.Figure | None:
    """
    Plots multiple modalities overlaid vertically into day-by-day rows (joyplot style).
    """
    from datetime import time
    
    pid = participant
    valid_mods = ["sleep", "hr", "stress", "activity", "spo2", "respiratory", "cgm"]
    modalities = [m.lower() for m in modalities if m.lower() in valid_mods]
    if not modalities or not loaded_data:
        return None
        
    MOD_COLORS = {"hr": "red", "stress": "orange", "spo2": "purple", "activity": "green", "respiratory": "#17becf", "cgm": "hotpink"}
    MOD_NAMES = {"hr": "Heart Rate", "stress": "Stress", "spo2": "SpO2", "activity": "Steps", "respiratory": "Resp Rate", "cgm": "Glucose"}
        
    # Figure out all logical days in the range
    logical_start_date = (start_dt - timedelta(hours=split_hour)).date()
    logical_end_date = (end_dt - timedelta(hours=split_hour)).date()
    
    date_keys_all = []
    curr = logical_start_date
    while curr <= logical_end_date:
        date_keys_all.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)
        
    # Remap loaded_data to match old script expectations
    old_loaded_data = {}
    for mod in modalities:
        if mod == "sleep":
            old_loaded_data["sleep"] = loaded_data.get("sleep", {}).get("segments", [])
        elif mod == "activity":
            old_loaded_data["activity"] = loaded_data.get("activity", {}).get("epochs", [])
        else:
            old_loaded_data[mod] = loaded_data.get(mod, {}).get("df", pd.DataFrame())
                
    # Filter date_keys to only those that contain at least some data
    date_keys = []
    for dk in date_keys_all:
        dt_obj = datetime.strptime(dk, "%Y-%m-%d")
        ld_start = datetime.combine(dt_obj, datetime.min.time())
        if start_dt.tzinfo:
            ld_start = ld_start.replace(tzinfo=start_dt.tzinfo)
        ld_start += timedelta(hours=split_hour)
        ld_end = ld_start + timedelta(hours=24)
        
        has_data = False
        for mod in modalities:
            if has_data: break
            if mod == "sleep":
                for seg in old_loaded_data["sleep"]:
                    if seg["start"] < ld_end and seg["end"] > ld_start:
                        has_data = True; break
            elif mod == "activity":
                for ep in old_loaded_data["activity"]:
                    if ep["start"] < ld_end and ep["end"] > ld_start:
                        has_data = True; break
            else:
                df = old_loaded_data[mod]
                if not df.empty:
                    sub = df.loc[(df.index >= ld_start) & (df.index <= ld_end)]
                    if not sub.empty:
                        has_data = True; break
        
        if has_data:
            date_keys.append(dk)
            
    n_days = len(date_keys)
    if n_days == 0:
        return None
        
    plot_height = max(400, n_days * 200 + 150)
    v_spacing = 0.0
    if n_days > 1:
        # 30 pixels of vertical spacing as a fraction of the total plot height
        v_spacing = 30.0 / plot_height

    fig = make_subplots(
        rows=n_days, cols=1,
        shared_xaxes=True,
        vertical_spacing=v_spacing,
        subplot_titles=None
    )
    
    dummy_base = pd.Timestamp("1970-01-01") + pd.Timedelta(hours=split_hour)

    # 1. Plot Sleep (background rectangles and hover lines)
    if "sleep" in modalities:
        segments = old_loaded_data["sleep"]
        if segments:
            for seg in segments:
                if seg["end"] <= start_dt or seg["start"] >= end_dt:
                    continue
                x_start_dt = max(start_dt, seg["start"])
                x_end_dt   = min(end_dt, seg["end"])
                
                # Sleep segment might cross the split_hour (span multiple logical days)
                s_shifted = x_start_dt - timedelta(hours=split_hour)
                e_shifted = x_end_dt - timedelta(hours=split_hour)
                
                curr_start = s_shifted
                while curr_start < e_shifted:
                    curr_date = curr_start.date()
                    curr_date_key = curr_date.strftime("%Y-%m-%d")
                    
                    # End of this logical day is exactly 24h later in shifted time (00:00 next day)
                    end_of_day = datetime.combine(curr_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=s_shifted.tzinfo)
                    curr_end = min(e_shifted, end_of_day)
                    
                    if curr_date_key in date_keys:
                        row_idx = date_keys.index(curr_date_key) + 1
                        
                        h_start = curr_start.hour + curr_start.minute / 60.0 + curr_start.second / 3600.0
                        h_end = curr_end.hour + curr_end.minute / 60.0 + curr_end.second / 3600.0
                        if curr_end == end_of_day:
                            h_end = 24.0
                        
                        stage = seg["stage"]
                        color = STAGE_COLORS.get(stage, "#BDBDBD")
                        
                        dt_start_str = (curr_start + timedelta(hours=split_hour)).strftime("%Y-%m-%d %H:%M:%S")
                        dt_end_str = (curr_end + timedelta(hours=split_hour)).strftime("%Y-%m-%d %H:%M:%S")
                        
                        x0_dt = dummy_base + pd.Timedelta(hours=h_start)
                        x1_dt = dummy_base + pd.Timedelta(hours=h_end)
                        
                        # Background rectangle
                        fig.add_shape(
                            type="rect",
                            x0=x0_dt, y0=0, x1=x1_dt, y1=1.0,
                            fillcolor=color, line_width=0,
                            opacity=0.6,
                            layer="below",
                            row=row_idx, col=1
                        )
                        
                    curr_start = curr_end

    # Helper function for line modalities
    def plot_line_modality(mod_name, df_data, val_col="value"):
        if df_data.empty: return
        mask = (df_data.index >= start_dt) & (df_data.index <= end_dt)
        sub_df = df_data.loc[mask]
        if sub_df.empty: return
        # Fixed physiological boundaries for cross-participant comparability
        GLOBAL_BOUNDS = {
            "hr": (40, 180),          # Most daily HR lives in 40-180
            "stress": (0, 100),       # Garmin stress is strictly 0-100
            "spo2": (80, 100),        # Readings < 80 are extremely rare/artifacts
            "activity": (0, 200),     # Steps per minute! 200 spm is a very fast run
            "respiratory": (10, 30),  # Most breathing falls in 10-30 rpm
            "cgm": (50, 300)          # Normal to mildly extreme glucose range
        }
        
        # Fallback to dynamic if modality not found
        default_min = sub_df[val_col].min()
        default_max = sub_df[val_col].max()
        mod_min, mod_max = GLOBAL_BOUNDS.get(mod_name, (default_min, default_max))
        
        range_span = mod_max - mod_min if mod_max > mod_min else 1.0
        
        shifted = sub_df.index - pd.Timedelta(hours=split_hour)
        date_keys_series = shifted.strftime("%Y-%m-%d")
        hour_offsets = shifted.hour + shifted.minute / 60.0 + shifted.second / 3600.0
        
        # Calculate normalized value and clip to [0, 1] so extreme outliers don't bleed into the row above
        norm_raw = (sub_df[val_col] - mod_min) / range_span
        norm_vals = np.clip(norm_raw, 0.0, 1.0) * 0.9
        dt_strs = sub_df.index.strftime("%Y-%m-%d %H:%M:%S")
        
        temp_df = pd.DataFrame({
            "hour_offset": hour_offsets,
            "plot_time": dummy_base + pd.to_timedelta(hour_offsets, unit="h"),
            "norm_val": norm_vals,
            "true_val": sub_df[val_col],
            "date_key": date_keys_series,
            "dt_str": dt_strs
        })
        
        # Determine format based on modality
        fmt = ".1f" if mod_name in ["hr", "spo2", "stress", "respiratory", "activity"] else ".0f"
        units = " bpm" if mod_name == "hr" else " %" if mod_name == "spo2" else " rpm" if mod_name == "respiratory" else " mg/dL" if mod_name == "cgm" else " spm" if mod_name == "activity" else ""
        
        # Gap thresholds in hours (to break lines on missing data)
        thresholds_hr = {
            "hr": 5 / 60.0,
            "stress": 5 / 60.0,
            "spo2": 2.0, # sparse
            "activity": 20 / 60.0, # 15 min epochs
            "respiratory": 5 / 60.0,
            "cgm": 15 / 60.0 # Dexcom G6 is every 5 minutes
        }
        thresh = thresholds_hr.get(mod_name, 0.25)
        
        # Hover snap tolerances in hours
        hover_tols_hr = {
            "cgm": 5.1 / 60.0 # Allow snapping to closest CGM reading up to 5 mins away
        }
        tol = hover_tols_hr.get(mod_name, 1.1 / 60.0)
        
        for dk, group in temp_df.groupby("date_key"):
            if dk in date_keys:
                row_idx = date_keys.index(dk) + 1
                
                thresh_td = pd.Timedelta(hours=thresh)
                # Insert NaNs for gaps to break the plotly line
                group = group.sort_values("plot_time").reset_index(drop=True)
                diffs = group["plot_time"].diff()
                gap_idxs = group.index[diffs > thresh_td]
                
                line_df = group.copy()
                if len(gap_idxs) > 0:
                    nan_rows = []
                    for idx in gap_idxs:
                        r_start = line_df.loc[idx - 1].copy()
                        r_start["plot_time"] = r_start["plot_time"] + pd.Timedelta(microseconds=1)
                        r_start["norm_val"] = None
                        
                        r_end = line_df.loc[idx].copy()
                        r_end["plot_time"] = r_end["plot_time"] - pd.Timedelta(microseconds=1)
                        r_end["norm_val"] = None
                        
                        nan_rows.extend([r_start, r_end])
                    line_df = pd.concat([line_df, pd.DataFrame(nan_rows)], ignore_index=True).sort_values("plot_time")
                
                # Trace 1: The visible broken line (No hover)
                fig.add_trace(go.Scatter(
                    x=line_df["plot_time"],
                    y=line_df["norm_val"],
                    mode="lines" if mod_name != "spo2" else "lines+markers",
                    line=dict(color=MOD_COLORS[mod_name], width=1.5),
                    marker=dict(size=4) if mod_name == "spo2" else None,
                    name=MOD_NAMES[mod_name],
                    legendgroup=mod_name,
                    showlegend=False,
                    connectgaps=False,
                    hoverinfo="skip"
                ), row=row_idx, col=1)
                
                # Trace 2: The invisible dense grid (Forces exact 1-minute hover and NAN display)
                grid_x = dummy_base + pd.to_timedelta(np.arange(0, 24 * 60), unit="m")
                grid_df = pd.DataFrame({"plot_time": grid_x})
                
                # Ensure exactly matching dtypes to prevent pandas MergeError
                grid_df["plot_time"] = grid_df["plot_time"].astype("datetime64[ns]")
                group["plot_time"] = group["plot_time"].astype("datetime64[ns]")
                
                merged = pd.merge_asof(
                    grid_df, group,
                    on="plot_time",
                    direction="nearest",
                    tolerance=pd.Timedelta(hours=tol)
                )
                
                # Keep y valid so it stays in the unified hover, interpolate to track the line
                hover_y = merged["norm_val"].interpolate().bfill().ffill().fillna(0.5)
                
                hover_texts = []
                for val, dt_s in zip(merged["true_val"], merged["dt_str"]):
                    if pd.isna(val):
                        hover_texts.append("NAN")
                    else:
                        hover_texts.append(f"{val:{fmt}}{units} ({dt_s[11:]})")
                        
                fig.add_trace(go.Scatter(
                    x=merged["plot_time"],
                    y=hover_y,
                    mode="markers",
                    marker=dict(color="rgba(0,0,0,0)", size=1), # Invisible
                    name=MOD_NAMES[mod_name],
                    legendgroup=mod_name,
                    showlegend=False,
                    hovertemplate=f"{MOD_NAMES[mod_name]}: %{{customdata}}<extra></extra>",
                    customdata=hover_texts
                ), row=row_idx, col=1)

    # 2. Plot Continuous Modalities
    if "hr" in modalities:
        plot_line_modality("hr", old_loaded_data["hr"])
    if "stress" in modalities:
        plot_line_modality("stress", old_loaded_data["stress"])
    if "spo2" in modalities:
        plot_line_modality("spo2", old_loaded_data["spo2"])
    if "respiratory" in modalities:
        plot_line_modality("respiratory", old_loaded_data["respiratory"])
    if "cgm" in modalities:
        plot_line_modality("cgm", old_loaded_data["cgm"])

    # 3. Plot Activity as line
    if "activity" in modalities:
        epochs = old_loaded_data["activity"]
        if epochs:
            ep_window = [e for e in epochs if e["end"] > start_dt and e["start"] < end_dt]
            if ep_window:
                ep_df = pd.DataFrame(ep_window)
                # Compute steps per minute because epochs are variable length (1-10 mins)
                ep_df["steps_per_min"] = ep_df["steps"] / ep_df["duration_min"]
                ep_df.set_index("start", inplace=True)
                plot_line_modality("activity", ep_df, val_col="steps_per_min")

    # Custom Legends
    if "sleep" in modalities:
        for stage, color in STAGE_COLORS.items():
            if stage == "wake": continue
            fig.add_trace(go.Scatter(
                x=[None], y=[None],
                mode="markers",
                marker=dict(color=color, size=10, symbol="square"),
                name=f"Sleep: {stage.upper()}"
            ))
            
    for mod in modalities:
        if mod == "sleep": continue
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="lines" if mod != "spo2" else "lines+markers",
            line=dict(color=MOD_COLORS[mod], width=2),
            marker=dict(size=6, color=MOD_COLORS[mod]) if mod == "spo2" else None,
            name=MOD_NAMES[mod]
        ))

    fig.update_layout(
        title=f"Multimodal Data — {pid} (Split: {split_hour:02d}:00)",
        plot_bgcolor="white",
        height=max(400, n_days * 200 + 150),
        hovermode="x unified"
    )
    
    # Configure axes for each subplot
    for i, dk in enumerate(date_keys):
        row_idx = i + 1
        # X axes: show short hour ticks on all rows
        fig.update_xaxes(
            range=[dummy_base, dummy_base + pd.Timedelta(hours=24)],
            showgrid=True, gridcolor="rgba(0,0,0,0.1)",
            tickformat="%H", # Show hour as integer
            hoverformat="%H:%M", # HH:MM for hover box
            showticklabels=True,
            tickfont=dict(size=10),
            dtick=3600000 * 2, # Every 2 hours
            row=row_idx, col=1
        )
        if row_idx == n_days:
            fig.update_xaxes(title="Time of Day", row=row_idx, col=1)
            
        # Parse date_key to get day of week
        dt_obj = datetime.strptime(dk, "%Y-%m-%d")
        display_label = f"{dt_obj.strftime('%A')}<br>{dk}"
        
        # Y axes: Title is the date + day, range is 0 to 1
        fig.update_yaxes(
            title_text=display_label,
            title_font=dict(size=11),
            range=[0, 1.05],
            showgrid=False, zeroline=False, showticklabels=False,
            row=row_idx, col=1
        )

    fig.update_layout(margin=dict(b=40))
    
    if return_fig:
        return fig
    return None
