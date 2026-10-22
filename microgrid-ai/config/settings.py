"""Project-wide configuration for the microgrid monitoring platform.

All paths are resolved relative to the repository root so the project can be
moved or copied without editing source files.  Numeric defaults for the
dashboard are the *initial* values; the ones stored in SQLite (table
``settings``) always win so they can be changed at runtime from the Settings
page.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
BACKEND_DIR = BASE_DIR / "backend"
ML_DIR = BASE_DIR / "ml"
DATA_DIR = BASE_DIR / "data"
DATASET_DIR = DATA_DIR / "dataset"
DB_DIR = DATA_DIR / "db"
ARTIFACTS_DIR = ML_DIR / "artifacts"
REPORTS_DIR = BASE_DIR / "reports"
GRAPHS_DIR = REPORTS_DIR / "graphs"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
TESTS_DIR = BASE_DIR / "tests"

DATABASE_PATH = Path(os.environ.get("MICROGRID_DB", DB_DIR / "microgrid.db"))
DATASET_PATH = Path(
    os.environ.get("MICROGRID_DATASET", DATASET_DIR / "microgrid_dataset.csv")
)

# --------------------------------------------------------------------------- #
# Model artifacts
# --------------------------------------------------------------------------- #
GENERATION_MODEL_FILE = ARTIFACTS_DIR / "generation_model.joblib"
CONDITION_MODEL_FILE = ARTIFACTS_DIR / "condition_model.joblib"
ANOMALY_MODEL_FILE = ARTIFACTS_DIR / "anomaly_model.joblib"
FEATURE_SCALER_FILE = ARTIFACTS_DIR / "feature_scaler.joblib"
FEATURE_NAMES_FILE = ARTIFACTS_DIR / "feature_names.joblib"
MODEL_META_FILE = ARTIFACTS_DIR / "model_meta.json"
METRICS_FILE = ARTIFACTS_DIR / "metrics.json"
DATASET_SCHEMA_FILE = ARTIFACTS_DIR / "dataset_schema.json"

# Feature columns consumed by every model (order matters).
# The last three are engineered diagnostics computed from the raw sensor vector
# plus fixed hardware constants; they are the signals a real technician would
# use (Vmp deficit against the clean V(G) curve, generator volts-per-RPM, and
# LDR/irradiance agreement).  No target value is used to build them.
FEATURE_COLUMNS = [
    "hour",
    "day_of_year",
    "solar_irradiance_wm2",
    "solar_voltage",
    "wind_voltage",
    "turbine_rpm",
    "temperature_c",
    "humidity_percent",
    "light_level_lux",
    "solar_v_deficit",
    "wind_v_per_rpm",
    "lux_per_irradiance",
]

# Hardware constants shared by the simulator and the feature engineer so the
# training pipeline and the live inference service stay consistent.
SOLAR_VOC = 6.0            # V, small 6 V / 1.5 W panel
SOLAR_IRR_REF = 350.0      # W/m2, characteristic irradiance of the V(G) curve
SOLAR_TEMP_COEF = 0.0035   # 1/K, Voc temperature coefficient

# The node has no pyranometer, so irradiance is inferred from the LDR module.
# These are the inverse of the relationship used by the simulator, so training
# and live inference stay consistent.  Re-derive them from a real pyranometer
# log before trusting live predictions.
LUX_OFFSET = 12.0
LUX_SCALE = 118000.0
LUX_EXPONENT = 1.25
LUX_PER_STATUS = {"bright": 80000.0, "dim": 8000.0, "dark": 20.0, "unknown": 8000.0}

REGRESSION_TARGET = "total_est_power_w"
CLASS_TARGET = "operating_condition"
ANOMALY_TARGET = "anomaly_label"

# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #
HOST = os.environ.get("MICROGRID_HOST", "0.0.0.0")
PORT = int(os.environ.get("MICROGRID_PORT", "5000"))
DEBUG = os.environ.get("MICROGRID_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("MICROGRID_SECRET", "microgrid-local-dev-key")

# --------------------------------------------------------------------------- #
# Runtime defaults persisted in SQLite (see backend/db.py: DEFAULT_SETTINGS)
# --------------------------------------------------------------------------- #
DEFAULT_SETTINGS = {
    "sampling_interval_s": "5",
    "dashboard_refresh_s": "5",
    "history_refresh_s": "30",
    "history_window_h": "24",
    "anomaly_threshold": "0.5",
    "optimize_reserve_w": "5.0",
    "optimize_load_high_w": "4.0",
    "optimize_load_low_w": "1.5",
    "device_offline_after_s": "90",
    "demo_mode": "1",
    "backend_url": "",
    "device_token": "demo-device-token-123",
    "default_device_id": "ESP8266-GRID-01",
    "relay_control_enabled": "0",
}

SETTING_TYPES = {
    "sampling_interval_s": int,
    "dashboard_refresh_s": int,
    "history_refresh_s": int,
    "history_window_h": int,
    "anomaly_threshold": float,
    "optimize_reserve_w": float,
    "optimize_load_high_w": float,
    "optimize_load_low_w": float,
    "device_offline_after_s": int,
    "demo_mode": int,
    "backend_url": str,
    "device_token": str,
    "default_device_id": str,
    "relay_control_enabled": int,
}

SETTING_BOUNDS = {
    "sampling_interval_s": (1, 3600),
    "dashboard_refresh_s": (1, 3600),
    "history_refresh_s": (5, 3600),
    "history_window_h": (1, 720),
    "anomaly_threshold": (0.01, 0.99),
    "optimize_reserve_w": (0.0, 500.0),
    "optimize_load_high_w": (0.0, 500.0),
    "optimize_load_low_w": (0.0, 500.0),
    "device_offline_after_s": (10, 3600),
    "demo_mode": (0, 1),
    "relay_control_enabled": (0, 1),
}


def ensure_directories() -> None:
    """Create every writable directory the application needs."""
    for path in (DATASET_DIR, DB_DIR, ARTIFACTS_DIR, GRAPHS_DIR):
        path.mkdir(parents=True, exist_ok=True)
