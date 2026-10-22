"""Dataset loading, feature engineering and leakage-free chronological splitting.

The split is strictly time ordered (train -> validation -> test).  A random
shuffle would let the model see the future and would inflate every metric, so
it is deliberately not used here.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402

# Columns measured (or estimated) by the node itself.  These are what the
# inference service may use at run time; `hour`/`day_of_year` are derived from
# the reading timestamp.
RAW_SENSOR_COLUMNS = [
    "solar_voltage",
    "solar_irradiance_wm2",
    "wind_voltage",
    "turbine_rpm",
    "temperature_c",
    "humidity_percent",
    "light_level_lux",
]

TRAIN_FRACTION = 0.70
VAL_FRACTION = 0.15
TEST_FRACTION = 0.15


def load_dataset(path: Path | str | None = None) -> pd.DataFrame:
    """Load the CSV, coerce types and fail loudly on a bad file."""
    csv_path = Path(path) if path else settings.DATASET_PATH
    if not csv_path.exists():
        raise FileNotFoundError(
            "Dataset not found at %s. Run `python -m ml.generate_dataset` first."
            % csv_path
        )

    frame = pd.read_csv(csv_path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    if frame["timestamp"].isna().any():
        raise ValueError("Dataset contains unparseable timestamps")

    for column in RAW_SENSOR_COLUMNS + ["total_est_power_w", "anomaly_label"]:
        if column not in frame.columns:
            raise ValueError("Dataset is missing required column: %s" % column)
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if "operating_condition" not in frame.columns:
        raise ValueError("Dataset is missing required column: operating_condition")

    frame = frame.sort_values("timestamp").reset_index(drop=True)
    return frame


def _lux_to_irradiance(lux: float) -> float:
    """Invert the simulator's LDR curve: lux -> W/m2 (clipped to 0..1200)."""
    if not math.isfinite(lux) or lux <= settings.LUX_OFFSET:
        return 0.0
    ratio = (lux - settings.LUX_OFFSET) / settings.LUX_SCALE
    return float(np.clip(
        1000.0 * np.power(max(ratio, 0.0), 1.0 / settings.LUX_EXPONENT),
        0.0, 1200.0))


def irradiance_from_lux(lux: Optional[float],
                        light_status: Optional[str] = None) -> float:
    """Infer irradiance (W/m2) from the LDR reading.

    The node has no pyranometer, so this inverse of the simulator's LDR curve
    is the only estimate available.  When the analogue lux value is missing the
    coarse ``light_status`` word is mapped to a representative lux level and run
    through the same curve, which is far less accurate and is reported as such
    to the caller.  The return value is always an irradiance in W/m2 - never a
    raw lux figure.
    """
    if lux is not None:
        try:
            value = float(lux)
        except (TypeError, ValueError):
            value = None
        if value is not None and math.isfinite(value):
            return _lux_to_irradiance(value)

    status = (light_status or "unknown").strip().lower()
    representative_lux = float(
        settings.LUX_PER_STATUS.get(status, settings.LUX_PER_STATUS["unknown"]))
    return _lux_to_irradiance(representative_lux)


def engineer_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add time features plus the three diagnostic features.

    ``solar_v_deficit``   How far the measured panel voltage sits below the
                          clean single-diode-style V(G) curve for the current
                          irradiance and cell temperature.  Partial shading and
                          heavy soiling show up here first.
    ``wind_v_per_rpm``    Effective generator constant.  A fouled rotor or a
                          failing rectifier produces fewer volts per RPM.
    ``lux_per_irradiance`` Agreement between the LDR and the irradiance
                          estimate; a stuck or shaded LDR desynchronises them.
    """
    out = frame.copy()
    stamp = out["timestamp"]
    out["hour"] = stamp.dt.hour + stamp.dt.minute / 60.0
    out["day_of_year"] = stamp.dt.dayofyear

    irradiance = out["solar_irradiance_wm2"].astype(float)
    temperature = out["temperature_c"].astype(float)
    rpm = out["turbine_rpm"].astype(float)

    thermal = 1.0 - settings.SOLAR_TEMP_COEF * (temperature - 25.0)
    expected_solar_v = (
        settings.SOLAR_VOC
        * (1.0 - np.exp(-irradiance / settings.SOLAR_IRR_REF))
        * thermal
    )
    out["solar_v_deficit"] = (expected_solar_v - out["solar_voltage"].astype(float)).round(4)
    out["wind_v_per_rpm"] = (
        out["wind_voltage"].astype(float) / np.maximum(rpm, 1.0)
    ).round(6)
    out["lux_per_irradiance"] = (
        out["light_level_lux"].astype(float) / np.maximum(irradiance, 1.0)
    ).round(4)

    missing = [c for c in settings.FEATURE_COLUMNS if c not in out.columns]
    if missing:
        raise ValueError("Cannot build features, missing columns: %s" % missing)
    return out


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the model input matrix (raw sensors + engineered diagnostics)."""
    return engineer_features(frame)


def chronological_split(
    frame: pd.DataFrame,
    train: float = TRAIN_FRACTION,
    val: float = VAL_FRACTION,
    test: float = TEST_FRACTION,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Time-ordered 70/15/15 split.  Rows must already be sorted by timestamp."""
    if abs(train + val + test - 1.0) > 1e-9:
        raise ValueError("train/val/test fractions must sum to 1.0")
    n = len(frame)
    train_end = int(n * train)
    val_end = int(n * (train + val))
    return (
        frame.iloc[:train_end].reset_index(drop=True),
        frame.iloc[train_end:val_end].reset_index(drop=True),
        frame.iloc[val_end:].reset_index(drop=True),
    )


def matrix(
    frame: pd.DataFrame, target: str
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Return X, y and the feature-name list for one supervised target."""
    features = build_features(frame)
    x = features[settings.FEATURE_COLUMNS].to_numpy(dtype=float)
    y = features[target]
    if target == settings.ANOMALY_TARGET:
        y = y.astype(int)
    else:
        y = y.astype(str)
    return x, y, list(settings.FEATURE_COLUMNS)


def prepare_all(
    path: Path | str | None = None,
) -> Dict[str, object]:
    """Load, feature-engineer and split once; every model reuses the result."""
    frame = load_dataset(path)
    enriched = build_features(frame)
    train_df, val_df, test_df = chronological_split(enriched)

    bundles = {}
    for split_name, split_frame in (
        ("train", train_df),
        ("val", val_df),
        ("test", test_df),
    ):
        bundles[split_name] = split_frame

    return {
        "full": enriched,
        "train": train_df,
        "val": val_df,
        "test": test_df,
        "splits": bundles,
        "n_rows": len(enriched),
        "n_train": len(train_df),
        "n_val": len(val_df),
        "n_test": len(test_df),
        "feature_columns": list(settings.FEATURE_COLUMNS),
        "time_range": {
            "start": str(enriched["timestamp"].min()),
            "end": str(enriched["timestamp"].max()),
        },
        "anomaly_rate": float(enriched[settings.ANOMALY_TARGET].mean()),
        "condition_counts": {
            str(k): int(v)
            for k, v in enriched[settings.CLASS_TARGET].value_counts().items()
        },
    }


def dataset_schema(frame: pd.DataFrame) -> Dict[str, object]:
    """Human/machine readable description of the dataset contract."""
    schema: Dict[str, object] = {
        "n_rows": int(len(frame)),
        "n_columns": int(len(frame.columns)),
        "columns": {},
        "feature_columns": list(settings.FEATURE_COLUMNS),
        "targets": {
            "regression": settings.REGRESSION_TARGET,
            "classification": settings.CLASS_TARGET,
            "anomaly": settings.ANOMALY_TARGET,
        },
    }
    for column in frame.columns:
        series = frame[column]
        entry: Dict[str, object] = {"dtype": str(series.dtype)}
        if pd.api.types.is_numeric_dtype(series):
            entry["min"] = float(series.min())
            entry["max"] = float(series.max())
            entry["mean"] = float(series.mean())
            entry["nulls"] = int(series.isna().sum())
        else:
            entry["n_unique"] = int(series.nunique())
        schema["columns"][column] = entry
    return schema


def write_schema(frame: pd.DataFrame) -> Path:
    settings.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = settings.DATASET_SCHEMA_FILE
    path.write_text(json.dumps(dataset_schema(frame), indent=2), encoding="utf-8")
    return path
