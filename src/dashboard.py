"""
AIREADI v3 — Interactive QC Dashboard
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from config import DATA_ROOT, OUTPUT_ROOT
from loader import DataLoader
from visualizations import plot_multimodal
from cohort_explorer import render_cohort_explorer, load_cohort_data

st.set_page_config(page_title="AIREADI Dashboard", layout="wide")

loader = DataLoader()

@st.cache_data
def load_all_data(pid: str):
    data = {}
    seg, tz = loader.load_sleep_json(pid)
    data["sleep"] = {"segments": seg, "tz": tz}
    
    df_hr, _ = loader.load_heartrate_json(pid)
    data["hr"] = {"df": df_hr}
    
    df_stress, _ = loader.load_stress_json(pid)
    data["stress"] = {"df": df_stress}
    
    df_spo2, _ = loader.load_spo2_json(pid)
    data["spo2"] = {"df": df_spo2}
    
    epochs, _ = loader.load_activity_json(pid)
    data["activity"] = {"epochs": epochs}
    
    df_resp, _ = loader.load_respiratory_json(pid)
    data["respiratory"] = {"df": df_resp}
    
    df_cgm, _ = loader.load_cgm_json(pid)
    data["cgm"] = {"df": df_cgm}
    
    return data

@st.cache_data
def get_cached_participants():
    return loader.load_participants()
    
@st.cache_data
def get_cached_clinical_data(pid: str):
    clinical_data = {}
    cohort_data = load_cohort_data()
    for csv_name in ["measurement.csv", "observation.csv", "condition_occurrence.csv", "procedure_occurrence.csv"]:
        key = f"Clinical: {csv_name}"
        if key in cohort_data:
            df = cohort_data[key]
            if not df.empty:
                pid_col = "participant_id" if "participant_id" in df.columns else "person_id"
                try: pid_val = int(pid)
                except: pid_val = pid
                clinical_data[csv_name] = df[df[pid_col] == pid_val]
    return clinical_data

@st.cache_data
def load_csv_data(modality: str, suffix: str, pid: str):
    csv_path = OUTPUT_ROOT / f"{modality}_{suffix}.csv"
    if not csv_path.exists(): return pd.DataFrame()
    
    # Check column names for robustness
    sample_df = pd.read_csv(csv_path, nrows=0)
    pid_col = "person_id" if "person_id" in sample_df.columns else "participant_id"
    
    df = pd.read_csv(csv_path, dtype={pid_col: str})
    return df[df[pid_col] == pid.zfill(4)]

def main():
    st.markdown(
        """
        <style>
            /* Hide sidebar collapse button */
            [data-testid="collapsedControl"],
            [data-testid="stSidebarCollapseButton"] {
                display: none !important;
            }
            /* Hide the top header which contains the Deploy button */
            [data-testid="stHeader"] {
                display: none !important;
            }
            /* Move content up by reducing top padding */
        [data-testid="stSidebar"] {
            padding-top: 0rem !important;
        }
        .block-container {
            padding-top: 2rem !important;
        }
        /* Hide default header */
        header {visibility: hidden;}
        
        /* Custom CSS to make st.radio look exactly like st.tabs */
        div.row-widget.stRadio > div[role="radiogroup"] {
            flex-direction: row;
            gap: 2rem;
            border-bottom: 1px solid rgba(49, 51, 63, 0.2);
            padding-bottom: 0px;
        }
        div[role="radiogroup"] > label {
            margin-bottom: 0px !important;
            padding-bottom: 8px !important;
            cursor: pointer;
        }
        /* Hide the actual radio circles */
        div[role="radiogroup"] > label > div:first-child {
            display: none !important;
        }
        /* Style the active selected text with a red underline */
        div[role="radiogroup"] > label:has(input:checked),
        div[role="radiogroup"] > label:has(input[aria-checked="true"]) {
            border-bottom: 3px solid #ff4b4b;
            color: #ff4b4b;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    st.title("AI-READI: Flagship Type 2 Diabetes Dataset Explorer")
    
    # Custom Stateful Tabs using styled Radio buttons
    active_tab = st.radio("Navigation", ["Cohort Explorer", "Individual Participant"], horizontal=True, label_visibility="collapsed", key="active_tab")
    st.write("") # Spacing
    
    if active_tab == "Cohort Explorer":
        render_cohort_explorer()
    else:
        # Sidebar ONLY renders when Individual Participant is active!
        with st.sidebar:
            st.header("1. Select Participant")
            pid_input = st.text_input("Participant ID (e.g., 1001):", key="pid_input")
            load_btn = st.button("Load Data", type="primary", key="load_btn")
            
        render_individual_view(pid_input, load_btn)

def render_individual_view(pid_input, load_btn):
    if "loaded_pid" not in st.session_state: st.session_state.loaded_pid = None
    if load_btn and pid_input: st.session_state.loaded_pid = pid_input.strip()
    pid = st.session_state.loaded_pid
    if not pid:
        st.info("👈 Enter a participant ID in the sidebar to begin.")
        return
        
    st.subheader(f"Participant Summary: {pid}")
    
    # Load and show demographics
    participants = get_cached_participants()
    if not participants.empty:
        try: pid_int = int(pid)
        except: pid_int = pid
        pid_col = "person_id" if "person_id" in participants.columns else "participant_id"
        p_row = participants[participants[pid_col] == pid_int]
        if not p_row.empty:
            cols = st.columns(4)
            cols[0].metric("Age", p_row.iloc[0].get("age", "N/A"))
            cols[1].metric("Study Group", p_row.iloc[0].get("study_group", "N/A"))
            cols[2].metric("Clinical Site", p_row.iloc[0].get("clinical_site", "N/A"))
            cols[3].metric("Visit Date", p_row.iloc[0].get("study_visit_date", "N/A"))
        else:
            st.warning("Participant not found in participants.tsv")
            
    # Clinical Data preview
    clinical_data = get_cached_clinical_data(pid)
    with st.expander("Clinical & Biomarker Data (Click to expand)"):
        for name, df in clinical_data.items():
            if not df.empty:
                st.markdown(f"**{name}** ({len(df)} records)")
                st.dataframe(df.head(100), width="stretch")
            else:
                st.markdown(f"*{name}* - No data found for this participant.")
                
    ecg_files = loader.list_ecg_files(pid)
    with st.expander("Resting ECG Data (Click to expand)"):
        if ecg_files:
            st.markdown(f"Found **{len(ecg_files)}** ECG files for this participant:")
            for f in ecg_files:
                st.markdown(f"- `{f}`")
        else:
            st.markdown("*No resting ECG data found for this participant.*")
                
    with st.spinner(f"Loading raw data for {pid}..."):
        preloaded_data = load_all_data(pid)
        
    has_sleep = len(preloaded_data["sleep"].get("segments", [])) > 0
    has_hr = not preloaded_data["hr"].get("df", pd.DataFrame()).empty
    has_stress = not preloaded_data["stress"].get("df", pd.DataFrame()).empty
    has_spo2 = not preloaded_data["spo2"].get("df", pd.DataFrame()).empty
    has_activity = len(preloaded_data["activity"].get("epochs", [])) > 0
    has_respiratory = not preloaded_data["respiratory"].get("df", pd.DataFrame()).empty
    has_cgm = not preloaded_data["cgm"].get("df", pd.DataFrame()).empty
    
    min_dts, max_dts = [], []
    if has_sleep:
        segs = preloaded_data["sleep"]["segments"]
        min_dts.append(min(s["start"] for s in segs))
        max_dts.append(max(s["end"] for s in segs))
    if has_activity:
        epochs = preloaded_data["activity"]["epochs"]
        min_dts.append(epochs[0]["start"])
        max_dts.append(epochs[-1]["end"])
    for mod in ["hr", "stress", "spo2", "respiratory", "cgm"]:
        df = preloaded_data[mod].get("df")
        if df is not None and not df.empty:
            min_dts.append(df.index.min())
            max_dts.append(df.index.max())
            
    if not min_dts or not max_dts:
        st.warning(f"No valid time-series data found for participant {pid}.")
        return
        
    min_dt, max_dt = min(min_dts), max(max_dts)
    tz = preloaded_data["sleep"].get("tz")
        
    with st.sidebar:
        with st.form("plot_settings"):
            update_btn = st.form_submit_button("Update Plot", type="primary", width="stretch")
            st.markdown("---")
            
            st.header("2. View Settings")
            split_hour = st.slider("Split Hour", 0, 23, 12)
            date_range = st.slider("Date Range", min_value=min_dt.date(), max_value=max_dt.date(), value=(min_dt.date(), min_dt.date() + timedelta(days=2)))
            
            st.header("3. Modalities")
            show_sleep = st.checkbox("Sleep", value=has_sleep, disabled=not has_sleep)
            show_hr = st.checkbox("Heart Rate", value=has_hr, disabled=not has_hr)
            show_stress = st.checkbox("Stress", value=has_stress, disabled=not has_stress)
            show_spo2 = st.checkbox("SpO2", value=has_spo2, disabled=not has_spo2)
            show_activity = st.checkbox("Activity", value=has_activity, disabled=not has_activity)
            show_respiratory = st.checkbox("Respiratory Rate", value=has_respiratory, disabled=not has_respiratory)
            show_cgm = st.checkbox("CGM", value=has_cgm, disabled=not has_cgm)
            
    mods = [m for m, show in zip(["sleep", "hr", "stress", "activity", "spo2", "respiratory", "cgm"], 
                                 [show_sleep, show_hr, show_stress, show_activity, show_spo2, show_respiratory, show_cgm]) if show]
                                 
    tab_raw, tab_daily, tab_summary = st.tabs(["Raw Data Plots", "Daily Computed Features", "Summary Features"])
    
    with tab_raw:
        with st.spinner("Generating multimodal plot..."):
            if tz:
                import pytz; from zoneinfo import ZoneInfo
                try: local_tz = ZoneInfo(str(tz))
                except: local_tz = tz
                start_dt = datetime.combine(date_range[0], datetime.min.time()).replace(tzinfo=local_tz)
                end_dt = datetime.combine(date_range[1], datetime.max.time()).replace(tzinfo=local_tz)
            else:
                start_dt = datetime.combine(date_range[0], datetime.min.time())
                end_dt = datetime.combine(date_range[1], datetime.max.time())
                
            fig = plot_multimodal(pid, start_dt, end_dt, mods, split_hour, preloaded_data, return_fig=True)
            if fig: st.plotly_chart(fig, width="stretch")
            else: st.warning("Could not generate plot.")
            
    with tab_daily:
        dfs = []
        for m, prefix in [("sleep", "sleep"), ("heartrate", "hr"), ("stress", "stress"), ("respiratory", "rr"), ("activity", "activity"), ("spo2", "spo2")]:
            suffix = "all_participants" if m == "sleep" else "all_participants_24h"
            df = load_csv_data(prefix, suffix, pid)
            if not df.empty:
                df = df.copy(); df.insert(0, "Modality", prefix.upper()); dfs.append(df)
        if dfs:
            for d in dfs:
                st.markdown(f"**{d['Modality'].iloc[0]}**")
                st.dataframe(d.drop(columns=["Modality", "participant_id", "person_id", "timezone"], errors="ignore"), width="stretch")
        else:
            st.info("No daily computed features found. Please ensure the aggregation scripts have been run. If these scripts are not yet available in the repository, please wait for an upcoming update as they will be released soon.")
            
    with tab_summary:
        dfs_sum = []
        for m, prefix in [("sleep", "sleep"), ("heartrate", "hr"), ("stress", "stress"), ("respiratory", "rr"), ("activity", "activity"), ("spo2", "spo2")]:
            suffix = "participant_summary" if m == "sleep" else "participant_summary_24h"
            df = load_csv_data(prefix, suffix, pid)
            if not df.empty:
                df = df.copy(); df.insert(0, "Modality", prefix.upper()); dfs_sum.append(df)
        if dfs_sum:
            for d in dfs_sum:
                st.markdown(f"**{d['Modality'].iloc[0]}**")
                st.dataframe(d.drop(columns=["Modality", "participant_id", "person_id", "timezone"], errors="ignore").T.astype(str), width="stretch")
        else:
            st.info("No summary features found. Please ensure the aggregation scripts have been run. If these scripts are not yet available in the repository, please wait for an upcoming update as they will be released soon.")

if __name__ == "__main__":
    main()
