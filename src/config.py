"""
AIREADI v3 Preprocessing Pipeline — Shared Configuration
=========================================================
"""

import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

PIPELINE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT  = PIPELINE_ROOT.parent

# User's data structure
DATA_ROOT = PROJECT_ROOT / "data" / "raw"
OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed"

PARTICIPANT_TZ_MAP: dict[str, ZoneInfo] = {
    "1": ZoneInfo("America/Los_Angeles"),
    "4": ZoneInfo("America/Los_Angeles"),
    "7": ZoneInfo("America/Chicago"),
}

SHORT_TZ_MAP: dict[str, str] = {
    "pst":      "America/Los_Angeles",
    "pdt":      "America/Los_Angeles",
    "pacific":  "America/Los_Angeles",
    "cst":      "America/Chicago",
    "cdt":      "America/Chicago",
    "central":  "America/Chicago",
    "est":      "America/New_York",
    "edt":      "America/New_York",
    "eastern":  "America/New_York",
    "mst":      "America/Denver",
    "mdt":      "America/Denver",
    "mountain": "America/Denver",
    "utc":      "UTC",
    "gmt":      "UTC",
}

_UTC = ZoneInfo("UTC")

def resolve_timezone(header_tz: str | None, participant_id: str) -> ZoneInfo:
    if header_tz:
        tz_key = header_tz.strip().lower()
        if tz_key in SHORT_TZ_MAP:
            return ZoneInfo(SHORT_TZ_MAP[tz_key])
        try:
            return ZoneInfo(header_tz.strip())
        except (KeyError, ValueError):
            pass

    if not participant_id:
        raise ValueError("Empty participant ID")
    prefix = participant_id[0]
    if prefix not in PARTICIPANT_TZ_MAP:
        raise ValueError(f"Unknown participant ID prefix '{prefix}'")
    return PARTICIPANT_TZ_MAP[prefix]

def parse_utc(s: str) -> datetime:
    s = s.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_UTC)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s}")

# Heart rate
HR_MIN_PLAUSIBLE = 30
HR_MAX_PLAUSIBLE = 220

# Respiratory rate
RR_MIN_PLAUSIBLE = 5.0
RR_MAX_PLAUSIBLE = 40.0

# Oxygen saturation
SPO2_MIN_PLAUSIBLE = 70
SPO2_MAX_PLAUSIBLE = 100

# Continuous Glucose Monitoring
GLUCOSE_MIN_VALID = 20
GLUCOSE_MAX_VALID = 500

# Stress
STRESS_MIN_VALID = 0
STRESS_MAX_VALID = 100

# Activity
MAX_EPOCH_MIN = 1440

def setup_logging(name: str = "aireadi", level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(level=level, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
    return logging.getLogger(name)

log = setup_logging()
