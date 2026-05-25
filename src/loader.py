"""
AIREADI v3 Preprocessing Pipeline — Raw Data Loaders (Refactored)
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

from config import (
    DATA_ROOT, resolve_timezone, parse_utc,
    HR_MIN_PLAUSIBLE, HR_MAX_PLAUSIBLE, RR_MIN_PLAUSIBLE, RR_MAX_PLAUSIBLE,
    SPO2_MIN_PLAUSIBLE, SPO2_MAX_PLAUSIBLE, GLUCOSE_MIN_VALID, GLUCOSE_MAX_VALID,
    STRESS_MIN_VALID, STRESS_MAX_VALID, MAX_EPOCH_MIN
)
from qc_tracker import update_qc_tracker

log = logging.getLogger(__name__)

class DataLoader:
    def __init__(self, data_root: Path | str = DATA_ROOT):
        self.data_root = Path(data_root)

    def _read_json(self, filepath: Path) -> dict | None:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            log.error("Failed to read %s: %s", filepath, exc)
            return None

    def _resolve_tz_from_json(self, data: dict, pid: str) -> ZoneInfo:
        header = data.get("header") or {}
        header_tz = header.get("timezone")
        return resolve_timezone(header_tz, pid)

    def _find_json_file(self, modality_dir: str, pid: str, filename_suffix: str) -> Path | None:
        base_dir = self.data_root / "wearable_activity_monitor" / modality_dir / "garmin_vivosmart5" / pid
        candidates = [
            base_dir / f"{pid}_{filename_suffix}.json",
            base_dir / f"{pid}.json",
        ]
        for c in candidates:
            if c.is_file():
                return c
        if base_dir.is_dir():
            jsons = list(base_dir.glob("*.json"))
            if len(jsons) == 1:
                return jsons[0]
        return None

    def discover_participants(self, modality_dir: str) -> list[str]:
        device_dir = self.data_root / "wearable_activity_monitor" / modality_dir / "garmin_vivosmart5"
        if not device_dir.is_dir():
            return []
        return sorted(d.name for d in device_dir.iterdir() if d.is_dir() and d.name[0].isdigit())

    def load_participants(self) -> pd.DataFrame:
        path = self.data_root / "participants.tsv"
        if not path.is_file():
            return pd.DataFrame()
        return pd.read_csv(path, sep="\t")

    def load_clinical_data(self, pid: str) -> dict[str, pd.DataFrame]:
        clinical_data = {}
        for csv_name in ["measurement.csv", "observation.csv", "condition_occurrence.csv", "procedure_occurrence.csv"]:
            path = self.data_root / "clinical_data" / csv_name
            if path.is_file():
                df = pd.read_csv(path, low_memory=False)
                pid_col = "person_id" if "person_id" in df.columns else "participant_id" if "participant_id" in df.columns else None
                if not pid_col: continue
                try: pid_val = int(pid)
                except: pid_val = pid
                clinical_data[csv_name] = df[df[pid_col] == pid_val]
        return clinical_data

    def list_ecg_files(self, pid: str) -> list[str]:
        base_dir = self.data_root / "cardiac_ecg" / "ecg_12lead" / "philips_tc30" / pid
        if not base_dir.is_dir():
            return []
        return [f.name for f in base_dir.iterdir() if f.is_file()]

    def load_sleep_json(self, pid: str) -> tuple[list[dict], ZoneInfo | None]:
        filepath = self._find_json_file("sleep", pid, "sleep")
        if not filepath: return [], None
        data = self._read_json(filepath)
        if not data: return [], None
        local_tz = self._resolve_tz_from_json(data, pid)
        raw_segments = data.get("body", {}).get("sleep", [])
        segments = []
        for seg in raw_segments:
            stage = seg.get("sleep_stage_state", "").lower()
            tf = seg.get("effective_time_frame") or seg.get("sleep_stage_time_frame", {})
            ti = tf.get("time_interval", {})
            start_str, end_str = ti.get("start_date_time", ""), ti.get("end_date_time", "")
            if not stage or not start_str or not end_str: continue
            try:
                start = parse_utc(start_str).astimezone(local_tz)
                end = parse_utc(end_str).astimezone(local_tz)
                if end > start:
                    segments.append({"stage": stage, "start": start, "end": end})
            except: pass
        return sorted(segments, key=lambda s: s["start"]), local_tz

    def load_activity_json(self, pid: str) -> tuple[list[dict], ZoneInfo | None]:
        filepath = self._find_json_file("physical_activity", pid, "activity")
        if not filepath: return [], None
        data = self._read_json(filepath)
        if not data: return [], None
        local_tz = self._resolve_tz_from_json(data, pid)
        raw_epochs = data.get("body", {}).get("activity", [])
        epochs = []
        for ep in raw_epochs:
            raw_val = ep.get("base_movement_quantity", {}).get("value", "")
            if raw_val in ("", None): continue
            try: steps = int(float(raw_val))
            except: continue
            tf = ep.get("effective_time_frame", {}).get("time_interval", {})
            start_str, end_str = tf.get("start_date_time", ""), tf.get("end_date_time", "")
            if not start_str or not end_str: continue
            try:
                start = parse_utc(start_str).astimezone(local_tz)
                end = parse_utc(end_str).astimezone(local_tz)
                duration_min = (end - start).total_seconds() / 60.0
                if duration_min <= MAX_EPOCH_MIN:
                    epochs.append({"steps": steps, "activity_name": ep.get("activity_name", "unknown"), "start": start, "end": end, "duration_min": duration_min})
            except: pass
        return sorted(epochs, key=lambda e: e["start"]), local_tz

    def _load_point_measurement_json(self, pid: str, modality_dir: str, filename_suffix: str, body_key: str, value_path: list[str], min_plausible: float, max_plausible: float) -> tuple[pd.DataFrame, ZoneInfo | None]:
        filepath = self._find_json_file(modality_dir, pid, filename_suffix)
        if not filepath: return pd.DataFrame(columns=["value"]), None
        data = self._read_json(filepath)
        if not data: return pd.DataFrame(columns=["value"]), None
        local_tz = self._resolve_tz_from_json(data, pid)
        raw_records = data.get("body", {}).get(body_key, [])
        timestamps, values = [], []
        for rec in raw_records:
            obj = rec
            for key in value_path: obj = obj.get(key) if isinstance(obj, dict) else None
            if obj is None: continue
            try: val = float(obj)
            except: continue
            ts_str = rec.get("effective_time_frame", {}).get("date_time", "")
            if not ts_str: continue
            try: ts = parse_utc(ts_str)
            except: continue
            if min_plausible <= val <= max_plausible and val not in {0, -1.0, -2.0}:
                timestamps.append(ts)
                values.append(val)
        if not values: return pd.DataFrame(columns=["value"]), local_tz
        idx = pd.DatetimeIndex(timestamps, tz="UTC")
        df = pd.DataFrame({"value": values}, index=idx).sort_index()
        df = df[~df.index.duplicated(keep="first")]
        df.index = df.index.tz_convert(local_tz)
        df.index.name = "timestamp"
        return df, local_tz

    def load_heartrate_json(self, pid: str) -> tuple[pd.DataFrame, ZoneInfo | None]:
        return self._load_point_measurement_json(pid, "heart_rate", "heartrate", "heart_rate", ["heart_rate", "value"], HR_MIN_PLAUSIBLE, HR_MAX_PLAUSIBLE)

    def load_respiratory_json(self, pid: str) -> tuple[pd.DataFrame, ZoneInfo | None]:
        return self._load_point_measurement_json(pid, "respiratory_rate", "respiratoryrate", "breathing", ["respiratory_rate", "value"], RR_MIN_PLAUSIBLE, RR_MAX_PLAUSIBLE)

    def load_spo2_json(self, pid: str) -> tuple[pd.DataFrame, ZoneInfo | None]:
        return self._load_point_measurement_json(pid, "oxygen_saturation", "oxygensaturation", "breathing", ["oxygen_saturation", "value"], SPO2_MIN_PLAUSIBLE, SPO2_MAX_PLAUSIBLE)

    def load_stress_json(self, pid: str) -> tuple[pd.DataFrame, ZoneInfo | None]:
        return self._load_point_measurement_json(pid, "stress", "stress", "stress", ["stress", "value"], STRESS_MIN_VALID, STRESS_MAX_VALID)

    def load_cgm_json(self, pid: str) -> tuple[pd.DataFrame, ZoneInfo | None]:
        base_dir = self.data_root / "wearable_blood_glucose" / "continuous_glucose_monitoring" / "dexcom_g6" / pid
        if not base_dir.is_dir(): return pd.DataFrame(columns=["value"]), None
        jsons = list(base_dir.glob("*.json"))
        local_tz, timestamps, values = None, [], []
        for filepath in jsons:
            data = self._read_json(filepath)
            if not data: continue
            if local_tz is None:
                try: local_tz = self._resolve_tz_from_json(data, pid)
                except: continue
            for rec in data.get("body", {}).get("cgm", []):
                if rec.get("event_type") != "EGV": continue
                try: val = float(rec["blood_glucose"]["value"])
                except: continue
                ts_str = rec.get("effective_time_frame", {}).get("time_interval", {}).get("start_date_time", "")
                if not ts_str: continue
                try: ts = parse_utc(ts_str)
                except: continue
                if GLUCOSE_MIN_VALID <= val <= GLUCOSE_MAX_VALID:
                    timestamps.append(ts)
                    values.append(val)
        if not values: return pd.DataFrame(columns=["value"]), local_tz
        idx = pd.DatetimeIndex(timestamps, tz="UTC")
        df = pd.DataFrame({"value": values}, index=idx).sort_index()
        df = df[~df.index.duplicated(keep="first")]
        df.index = df.index.tz_convert(local_tz)
        df.index.name = "timestamp"
        return df, local_tz
