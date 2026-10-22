"""Model inference service.

Loads the three joblib artifacts once, keeps them hot, and turns a raw device
reading into a generation estimate, an operating-condition label and an
anomaly score.  Nothing here is hard-coded: every number comes from the fitted
scikit-learn models on disk.

Re-training
-----------
``python -m ml.train`` replaces the artifacts in place.  The service detects a
newer ``model_meta.json`` timestamp and reloads automatically, so a retrain
picks up real sensor logs without restarting Flask.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

from config import settings
from ml import preprocess

REQUIRED_RAW_COLUMNS = [
    "solar_voltage",
    "wind_voltage",
    "turbine_rpm",
]

# Fallbacks used only when a sensor genuinely failed to report.  Taken from the
# training-set medians recorded in model_meta.json so the estimate degrades
# gracefully instead of returning NaN.
FALLBACK_DEFAULTS = {
    "temperature_c": 25.0,
    "humidity_percent": 55.0,
    "light_level_lux": 8000.0,
}


class ModelNotTrainedError(RuntimeError):
    """Raised when the dashboard asks for a prediction before training."""


class InferenceService:
    """Thread-safe, lazily loaded wrapper around the three models."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._models: Dict[str, Any] = {}
        self._meta: Dict[str, Any] = {}
        self._feature_names: List[str] = []
        self._loaded_at: Optional[float] = None
        self._artifact_mtime: Optional[float] = None
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #
    def _artifact_stamp(self) -> Optional[float]:
        paths = [settings.GENERATION_MODEL_FILE, settings.CONDITION_MODEL_FILE,
                 settings.ANOMALY_MODEL_FILE, settings.MODEL_META_FILE]
        stamps = [p.stat().st_mtime for p in paths if p.exists()]
        return max(stamps) if stamps else None

    def _load(self) -> None:
        with self._lock:
            missing = [str(p) for p in (
                settings.GENERATION_MODEL_FILE,
                settings.CONDITION_MODEL_FILE,
                settings.ANOMALY_MODEL_FILE,
            ) if not p.exists()]
            if missing:
                raise ModelNotTrainedError(
                    "Model artifacts are missing (%s). Run `python -m ml.train` "
                    "to train the models before requesting predictions."
                    % ", ".join(missing)
                )
            try:
                self._models["generation"] = joblib.load(settings.GENERATION_MODEL_FILE)
                self._models["condition"] = joblib.load(settings.CONDITION_MODEL_FILE)
                self._models["anomaly"] = joblib.load(settings.ANOMALY_MODEL_FILE)
                if settings.FEATURE_NAMES_FILE.exists():
                    self._feature_names = list(
                        joblib.load(settings.FEATURE_NAMES_FILE))
                else:
                    self._feature_names = list(settings.FEATURE_COLUMNS)
                if settings.MODEL_META_FILE.exists():
                    self._meta = json.loads(
                        settings.MODEL_META_FILE.read_text(encoding="utf-8"))
                else:
                    self._meta = {}
                self._artifact_mtime = self._artifact_stamp()
                self._loaded_at = time.time()
                self._last_error = None
            except Exception as exc:  # pragma: no cover - depends on artifact health
                self._last_error = "%s: %s" % (type(exc).__name__, exc)
                raise

    def ensure_loaded(self) -> None:
        with self._lock:
            stamp = self._artifact_stamp()
            if not self._models or (stamp and stamp != self._artifact_mtime):
                self._load()

    def is_ready(self) -> bool:
        try:
            self.ensure_loaded()
            return True
        except ModelNotTrainedError:
            return False
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Feature engineering for a single live reading
    # ------------------------------------------------------------------ #
    def reading_to_frame(self, reading: Dict[str, Any]) -> pd.DataFrame:
        """Convert one normalised DB/API reading into the model input frame."""
        lux = reading.get("light_level_lux")
        light_status = reading.get("light_status")
        irradiance = reading.get("solar_irradiance_wm2")
        if irradiance in (None, "", 0):
            irradiance = preprocess.irradiance_from_lux(lux, light_status)

        temperature = reading.get("temperature_c")
        humidity = reading.get("humidity_percent")
        degraded: List[str] = []
        if temperature in (None, ""):
            temperature = FALLBACK_DEFAULTS["temperature_c"]
            degraded.append("temperature_c")
        if humidity in (None, ""):
            humidity = FALLBACK_DEFAULTS["humidity_percent"]
            degraded.append("humidity_percent")
        if lux in (None, ""):
            lux = FALLBACK_DEFAULTS["light_level_lux"]
            degraded.append("light_level_lux")

        stamp = reading.get("reading_timestamp") or reading.get("timestamp")
        if not stamp:
            stamp = pd.Timestamp.now(tz="UTC").isoformat()

        frame = pd.DataFrame(
            [{
                "timestamp": pd.to_datetime(stamp, utc=True, errors="coerce")
                or pd.Timestamp.now(tz="UTC"),
                "solar_irradiance_wm2": float(irradiance),
                "solar_voltage": float(reading.get("solar_voltage") or 0.0),
                "wind_voltage": float(reading.get("wind_voltage") or 0.0),
                "turbine_rpm": float(reading.get("turbine_rpm") or 0.0),
                "temperature_c": float(temperature),
                "humidity_percent": float(humidity),
                "light_level_lux": float(lux),
            }]
        )
        frame.attrs["degraded_inputs"] = degraded
        return preprocess.engineer_features(frame)

    # ------------------------------------------------------------------ #
    # Prediction
    # ------------------------------------------------------------------ #
    def predict(self, reading: Dict[str, Any],
                threshold: Optional[float] = None) -> Dict[str, Any]:
        """Run every model on one reading and return a dashboard-ready result."""
        self.ensure_loaded()
        frame = self.reading_to_frame(reading)
        features = frame[self._feature_names].to_numpy(dtype=float)

        power = float(self._models["generation"].predict(features)[0])
        power = max(power, 0.0)

        condition = str(self._models["condition"].predict(features)[0])
        condition_proba = {
            str(label): round(float(probability), 4)
            for label, probability in zip(
                self._models["condition"].classes_,
                self._models["condition"].predict_proba(features)[0],
            )
        }

        anomaly_classes = list(self._models["anomaly"].classes_)
        anomaly_proba = self._models["anomaly"].predict_proba(features)[0]
        if 1 in anomaly_classes:
            anomaly_probability = float(anomaly_proba[list(anomaly_classes).index(1)])
        else:  # pragma: no cover - model always trained with both classes
            anomaly_probability = 0.0

        if threshold is None:
            threshold = 0.5
        anomaly_flag = int(anomaly_probability >= threshold)

        degraded = list(frame.attrs.get("degraded_inputs", []))
        return {
            "predicted_power_w": round(power, 4),
            "predicted_condition": condition,
            "condition_confidence": round(max(condition_proba.values()), 4),
            "condition_probabilities": condition_proba,
            "anomaly_probability": round(anomaly_probability, 4),
            "anomaly_flag": anomaly_flag,
            "anomaly_threshold": float(threshold),
            "model_version": self._meta.get("model_version", "unknown"),
            "data_origin": "predicted",
            "model_trained_on": self._meta.get("data_origin", "simulated"),
            "degraded_inputs": degraded,
            "features": {
                name: round(float(value), 6)
                for name, value in zip(self._feature_names, features[0])
            },
            "irradiance_estimate_wm2": round(
                float(frame["solar_irradiance_wm2"].iloc[0]), 2),
        }

    def predict_series(self, readings: List[Dict[str, Any]],
                       threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        """Batch predict over an ordered list of readings."""
        self.ensure_loaded()
        if not readings:
            return []
        frames = [self.reading_to_frame(row) for row in readings]
        combined = pd.concat(frames, ignore_index=True)
        features = combined[self._feature_names].to_numpy(dtype=float)

        power = np.maximum(self._models["generation"].predict(features), 0.0)
        condition = self._models["condition"].predict(features)
        anomaly_classes = list(self._models["anomaly"].classes_)
        anomaly_proba = self._models["anomaly"].predict_proba(features)
        if 1 in anomaly_classes:
            anomaly_probability = anomaly_proba[:, list(anomaly_classes).index(1)]
        else:  # pragma: no cover
            anomaly_probability = np.zeros(len(features))

        if threshold is None:
            threshold = 0.5

        return [
            {
                "timestamp": readings[i].get("reading_timestamp"),
                "actual_power_w": readings[i].get("total_est_power_w"),
                "predicted_power_w": round(float(power[i]), 4),
                "predicted_condition": str(condition[i]),
                "anomaly_probability": round(float(anomaly_probability[i]), 4),
                "anomaly_flag": int(anomaly_probability[i] >= threshold),
            }
            for i in range(len(readings))
        ]

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #
    def status(self) -> Dict[str, Any]:
        ready = self.is_ready()
        metrics: Dict[str, Any] = {}
        if settings.METRICS_FILE.exists():
            try:
                metrics = json.loads(settings.METRICS_FILE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                metrics = {}

        models_summary: Dict[str, Any] = {}
        for key, label in (("generation", "generation"),
                           ("condition", "condition"),
                           ("anomaly", "anomaly")):
            entry = metrics.get("models", {}).get(label, {})
            if not entry:
                continue
            test = entry.get("test", {})
            summary: Dict[str, Any] = {
                "type": entry.get("type"),
                "target": entry.get("target"),
                "test_n_samples": test.get("n_samples"),
            }
            if key == "generation":
                summary.update({
                    "mae": test.get("mae"),
                    "rmse": test.get("rmse"),
                    "r2": test.get("r2"),
                })
            elif key == "condition":
                summary.update({
                    "accuracy": test.get("accuracy"),
                    "f1_macro": test.get("f1_macro"),
                    "per_class": test.get("per_class"),
                })
            else:
                summary.update({
                    "accuracy": test.get("accuracy"),
                    "precision": test.get("precision"),
                    "recall": test.get("recall"),
                    "f1": test.get("f1"),
                    "confusion_matrix": test.get("confusion_matrix"),
                })
            models_summary[key] = summary

        return {
            "ready": ready,
            "last_error": self._last_error,
            "loaded_at_unix": self._loaded_at,
            "artifact_mtime_unix": self._artifact_mtime,
            "seconds_since_load": (
                round(time.time() - self._loaded_at, 2) if self._loaded_at else None
            ),
            "model_version": self._meta.get("model_version"),
            "trained_at_unix": self._meta.get("trained_at_unix"),
            "trained_on_rows": self._meta.get("n_training_rows"),
            "validation_rows": self._meta.get("n_validation_rows"),
            "test_rows": self._meta.get("n_test_rows"),
            "anomaly_rate_training": self._meta.get("anomaly_rate"),
            "split_strategy": self._meta.get("split_strategy"),
            "feature_columns": self._feature_names or list(settings.FEATURE_COLUMNS),
            "targets": {
                "regression": settings.REGRESSION_TARGET,
                "condition": settings.CLASS_TARGET,
                "anomaly": settings.ANOMALY_TARGET,
            },
            "training_data_origin": self._meta.get("data_origin", "simulated"),
            "limitations": self._meta.get("limitations", []),
            "models": models_summary,
        }

    def feature_importance(self) -> List[Dict[str, Any]]:
        """Feature importances of the generation regressor, from metrics.json."""
        if not self.is_ready():
            return []
        return _importance_from_metrics()


def _importance_from_metrics() -> List[Dict[str, Any]]:
    if not settings.METRICS_FILE.exists():
        return []
    try:
        metrics = json.loads(settings.METRICS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return metrics.get("models", {}).get("generation", {}).get("feature_importance", [])


SERVICE = InferenceService()
