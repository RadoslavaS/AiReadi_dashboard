import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

from config import DATA_ROOT
from loader import DataLoader

@st.cache_data
def load_cohort_data():
    """Load demographics and all clinical tables into a cached dict of DataFrames."""
    loader = DataLoader()
    data = {}
    
    # Demographics
    df_part = loader.load_participants()
    if not df_part.empty:
        # Standardize ID column
        if "person_id" in df_part.columns:
            df_part = df_part.rename(columns={"person_id": "participant_id"})
        data["Demographics (participants.tsv)"] = df_part
        
    # Clinical Data
    for csv_name in ["measurement.csv", "observation.csv", "condition_occurrence.csv", "procedure_occurrence.csv"]:
        path = DATA_ROOT / "clinical_data" / csv_name
        if path.is_file():
            df = pd.read_csv(path, low_memory=False)
            if "person_id" in df.columns:
                df = df.rename(columns={"person_id": "participant_id"})
            # To save memory and speed, drop columns that are mostly entirely NaN or useless for filtering
            # We keep the core OMOP columns needed for value mapping
            keep_cols = [c for c in df.columns if not c.endswith("_concept_id")]
            if "measurement_concept_id" in df.columns: keep_cols.append("measurement_concept_id")
            
            data[f"Clinical: {csv_name}"] = df[keep_cols]
            
    return data

def render_cohort_explorer():
    st.header("Cohort Explorer")
    st.markdown("Filter the AI-READI cohort by demographics and clinical variables to find participants of interest.")
    
    with st.spinner("Loading cohort data (this may take a moment on first load)..."):
        cohort_data = load_cohort_data()
        
    if not cohort_data:
        st.error("No cohort data found in Data_v3/raw.")
        return
        
    st.subheader("Dynamic Filters")
    
    # Manage dynamic rule IDs
    if "filter_rules" not in st.session_state:
        st.session_state.filter_rules = [0]
    if "next_rule_id" not in st.session_state:
        st.session_state.next_rule_id = 1
        
    def add_rule():
        if len(st.session_state.filter_rules) < 5:
            st.session_state.filter_rules.append(st.session_state.next_rule_id)
            st.session_state.next_rule_id += 1
            
    def remove_rule(rule_id):
        if rule_id in st.session_state.filter_rules:
            st.session_state.filter_rules.remove(rule_id)
            
    valid_pids_sets = []
    
    # Render rules
    for idx in st.session_state.filter_rules:
        st.markdown(f"**Filter Rule {st.session_state.filter_rules.index(idx) + 1}**")
        col1, col2, col3, col4 = st.columns([2, 2, 4, 1])
        
        with col4:
            st.button("❌ Remove", key=f"remove_{idx}", on_click=remove_rule, args=(idx,))
            
        with col1:
            file_choice = st.selectbox("Source Data", list(cohort_data.keys()), key=f"file_{idx}")
            df = cohort_data[file_choice]
            
        with col2:
            is_omop_long = "measurement_source_value" in df.columns and "value_as_number" in df.columns
            if is_omop_long:
                col_choices = ["(OMOP Long Format Test Picker)"] + list(df.columns)
            else:
                col_choices = list(df.columns)
                
            col_choice = st.selectbox("Column / Test", col_choices, key=f"col_{idx}")
            
        with col3:
            matching_pids = set()
            null_pids = set()
            
            if col_choice == "(OMOP Long Format Test Picker)":
                test_name_col = "measurement_source_value" if "measurement_source_value" in df.columns else "observation_source_value"
                unique_tests = sorted(df[test_name_col].dropna().astype(str).unique())
                selected_test = st.selectbox("Select Test / Measurement", unique_tests, key=f"omop_test_{idx}")
                
                if selected_test:
                    test_df = df[df[test_name_col] == selected_test]
                    
                    # Try to infer if it's numeric or date from value_as_number or value_as_string
                    has_num = "value_as_number" in test_df.columns and not test_df["value_as_number"].dropna().empty
                    has_str = "value_as_string" in test_df.columns and not test_df["value_as_string"].dropna().empty
                    
                    is_omop_date = False
                    parsed_omop_dates = None
                    if has_str and not has_num:
                        # Try parsing as date
                        temp_parsed = pd.to_datetime(test_df["value_as_string"], errors="coerce")
                        valid_count = temp_parsed.notna().sum()
                        total_count = test_df["value_as_string"].notna().sum()
                        # If more than 50% of the non-null strings parse as dates, treat as date
                        if total_count > 0 and (valid_count / total_count) > 0.5:
                            is_omop_date = True
                            parsed_omop_dates = temp_parsed
                            
                    if has_num:
                        real_vals = pd.to_numeric(test_df["value_as_number"], errors="coerce").dropna()
                        if len(real_vals) > 0:
                            min_v, max_v = float(real_vals.min()), float(real_vals.max())
                            if min_v == max_v:
                                st.info(f"All values are exactly {min_v}")
                                matching_pids = set(test_df["participant_id"].unique())
                            else:
                                range_val = st.slider("Value Range", min_value=min_v, max_value=max_v, value=(min_v, max_v), key=f"omop_range_{idx}")
                                mask = (test_df["value_as_number"] >= range_val[0]) & (test_df["value_as_number"] <= range_val[1])
                                matching = test_df[mask.fillna(False)]
                                matching_pids = set(matching["participant_id"].unique())
                                
                    elif is_omop_date:
                        real_dates = parsed_omop_dates.dropna()
                        if len(real_dates) > 0:
                            min_v, max_v = real_dates.min().date(), real_dates.max().date()
                            if min_v == max_v:
                                st.info(f"All dates are exactly {min_v}")
                                matching_pids = set(test_df["participant_id"].unique())
                            else:
                                range_val = st.slider("Date Range", min_value=min_v, max_value=max_v, value=(min_v, max_v), key=f"omop_date_{idx}")
                                mask = (parsed_omop_dates.dt.date >= range_val[0]) & (parsed_omop_dates.dt.date <= range_val[1])
                                matching = test_df[mask.fillna(False)]
                                matching_pids = set(matching["participant_id"].unique())
                                
                    else:
                        st.warning("No filterable values found for this test.")
                        
                    # Calculate nulls: Participants who DON'T have this test at all
                    all_pids = set(df["participant_id"].unique())
                    has_test_pids = set(test_df["participant_id"].unique())
                    null_pids = all_pids - has_test_pids
            else:
                series = df[col_choice]
                
                is_date = pd.api.types.is_datetime64_any_dtype(series)
                is_string_date = False
                parsed_dates = None
                
                # Heuristic Date Check - Fallback for non-native date columns
                if not is_date:
                    lower_name = col_choice.lower()
                    # Check if name implies date, force parsing
                    if "date" in lower_name or "time" in lower_name or "dat" in lower_name:
                        # Try coercion. If it's numeric like 20230501 it might need format but coerce handles many cases.
                        # Convert to string first to ensure stable parsing for mixed types
                        temp_parsed = pd.to_datetime(series.astype(str), errors="coerce")
                        if temp_parsed.notna().sum() > 0:
                            is_date = True
                            is_string_date = True
                            parsed_dates = temp_parsed
                            
                if is_date:
                    if not is_string_date:
                        parsed_dates = series
                    real_vals = parsed_dates.dropna()
                else:
                    real_vals = series.dropna()

                n_unique = real_vals.nunique()
                
                if n_unique == 0:
                    st.warning("No filterable values found.")
                elif n_unique == 1:
                    val = real_vals.iloc[0]
                    if is_date: val = val.date()
                    st.info(f"All values are exactly {val}")
                    matching_pids = set(df["participant_id"].unique())
                elif is_date:
                    min_v, max_v = real_vals.min().date(), real_vals.max().date()
                    range_val = st.slider("Date Range", min_value=min_v, max_value=max_v, value=(min_v, max_v), key=f"date_range_{idx}")
                    mask = (parsed_dates.dt.date >= range_val[0]) & (parsed_dates.dt.date <= range_val[1])
                    matching = df[mask.fillna(False)]
                    matching_pids = set(matching["participant_id"].unique())
                elif n_unique <= 6:
                    st.write("Select values:")
                    unique_vals = sorted(real_vals.unique())
                    
                    selected_vals = []
                    cols = st.columns(len(unique_vals))
                    for i, u_val in enumerate(unique_vals):
                        with cols[i]:
                            if st.checkbox(str(u_val), value=True, key=f"chk_{idx}_{i}"):
                                selected_vals.append(unique_vals[i])
                    
                    if selected_vals:
                        mask = series.isin(selected_vals)
                        matching = df[mask.fillna(False)]
                        matching_pids = set(matching["participant_id"].unique())
                elif n_unique <= 20 or not pd.api.types.is_numeric_dtype(series):
                    unique_vals = sorted(real_vals.dropna().astype(str).unique())
                        
                    if len(unique_vals) > 200:
                        st.warning("Too many unique values to display. Please choose a different column.")
                    else:
                        selected_vals = st.multiselect("Select Values", unique_vals, key=f"cat_{idx}")
                        if selected_vals:
                            mask = series.astype(str).isin(selected_vals)
                            matching = df[mask.fillna(False)]
                            matching_pids = set(matching["participant_id"].unique())
                else:
                    min_v, max_v = float(real_vals.min()), float(real_vals.max())
                    range_val = st.slider("Value Range", min_value=min_v, max_value=max_v, value=(min_v, max_v), key=f"range_{idx}")
                    mask = (series >= range_val[0]) & (series <= range_val[1])
                    matching = df[mask.fillna(False)]
                    matching_pids = set(matching["participant_id"].unique())
                            
                # Nulls for standard columns are just where the value is NaN
                null_pids = set(df[series.isna()]["participant_id"].unique())

            # Checkbox for missing values
            include_nulls = st.checkbox("Include participants with missing/empty values", key=f"nulls_{idx}")
            
            # Combine
            final_rule_pids = matching_pids
            if include_nulls:
                final_rule_pids = final_rule_pids.union(null_pids)
                
            # If the user hasn't selected anything in a multiselect and include_nulls is false, it might return 0.
            # But if it's completely empty, maybe we don't apply the filter? 
            # We will strictly apply the filter if it's evaluated.
            valid_pids_sets.append(final_rule_pids)
                            
        st.markdown("---")
        
    st.button("+ Add Rule", on_click=add_rule, disabled=len(st.session_state.filter_rules) >= 5)
            
    # Calculate intersecting cohort
    demo_df = cohort_data.get("Demographics (participants.tsv)", pd.DataFrame())
    if demo_df.empty:
        st.error("Missing base demographics.")
        return
        
    master_pids = set(demo_df["participant_id"].unique())
    
    final_pids = master_pids
    for pid_set in valid_pids_sets:
        final_pids = final_pids.intersection(pid_set)
        
    st.header("Cohort Results")
    st.metric("Total Matching Participants", len(final_pids))
    
    if len(final_pids) == 0:
        st.warning("No participants match all active filters.")
        return
        
    # Filter demographics to only matching
    matched_demo = demo_df[demo_df["participant_id"].isin(final_pids)]
    
    # Visuals
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        if "age" in matched_demo.columns:
            fig_age = px.histogram(matched_demo, x="age", title="Age Distribution", nbins=15)
            st.plotly_chart(fig_age, width="stretch")
            
    with col_v2:
        if "study_group" in matched_demo.columns:
            counts = matched_demo["study_group"].value_counts().reset_index()
            counts.columns = ["study_group", "count"]
            fig_group = px.bar(counts, x="study_group", y="count", title="Study Group Distribution", color="study_group")
            st.plotly_chart(fig_group, width="stretch")
            
    # Results Table
    st.subheader("Matching Participants Data")
    st.dataframe(matched_demo, width="stretch")
