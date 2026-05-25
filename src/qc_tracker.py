"""
Unified QC Tracker for AIREADI v3 Preprocessing Pipeline
"""
from __future__ import annotations
import pandas as pd
from pathlib import Path
from config import OUTPUT_ROOT

QC_FILE_NAME = "qc_tracking.csv"
_QC_DATA: dict[str, dict] = {}

def update_qc_tracker(pid: str, modality: str, qc_counts: dict, output_root: Path | None = None) -> None:
    if not qc_counts:
        return
    prefixed_counts = {f"{modality}_{k}": v for k, v in qc_counts.items()}
    if pid not in _QC_DATA:
        _QC_DATA[pid] = {}
    _QC_DATA[pid].update(prefixed_counts)

def flush_qc_tracker(output_root: Path | None = None) -> None:
    if not _QC_DATA:
        return
    root = output_root or OUTPUT_ROOT
    qc_path = root / QC_FILE_NAME
    
    if qc_path.is_file():
        df = pd.read_csv(qc_path, dtype={"participant_id": str})
    else:
        df = pd.DataFrame(columns=["participant_id"])
        
    new_df = pd.DataFrame.from_dict(_QC_DATA, orient="index")
    new_df.index.name = "participant_id"
    new_df = new_df.reset_index()
    
    df = df.set_index("participant_id")
    new_df = new_df.set_index("participant_id")
    df = new_df.combine_first(df)
    df = df.reset_index()
    
    cols = ["participant_id"] + sorted([c for c in df.columns if c != "participant_id"])
    df = df[cols]
    qc_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(qc_path, index=False)
    _QC_DATA.clear()
