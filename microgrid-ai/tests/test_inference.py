"""Inference service on the real trained artifacts.

Skipped automatically (rather than failed) if the models have not been trained,
so the suite stays honest on a fresh clone where ``python -m ml.train`` has not
run yet.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.inference import SERVICE
from config import settings

pytestmark = pytest.mark.skipif(
    not SERVICE.is_ready(), reason="models are not trained yet")


def _reading(**overrides):
    reading = {
        "reading_timestamp": "2026-03-01T11:00:00+00:00",
        "solar_voltage": 5.3,
        "wind_voltage": 2.6,
        "turbine_rpm": 620.0,
        "temperature_c": 31.0,
        "humidity_percent": 48.0,
        "light_level_lux": 72000.0,
        "light_status": "bright",
    }
    reading.update(overrides)
    return reading


def test_status_exposes_all_three_models():
    status = SERVICE.status()
    assert status["ready"] is True
    assert set(status["models"]) == {"generation", "condition", "anomaly"}
    assert status["training_data_origin"] == "simulated"
    assert status["feature_columns"] == list(settings.FEATURE_COLUMNS)
    assert status["limitations"]


def test_predict_returns_dashboard_ready_fields():
    result = SERVICE.predict(_reading())
    for key in ("predicted_power_w", "predicted_condition", "anomaly_probability",
                "anomaly_flag", "model_version", "features",
                "irradiance_estimate_wm2", "degraded_inputs"):
        assert key in result
    assert result["predicted_power_w"] >= 0.0
    assert 0.0 <= result["anomaly_probability"] <= 1.0
    assert result["anomaly_flag"] in (0, 1)
    assert result["predicted_condition"] in {
        "normal", "reduced_generation", "night_idle", "fault"}
    assert result["data_origin"] == "predicted"
    assert set(result["features"]) == set(settings.FEATURE_COLUMNS)


def test_condition_probabilities_sum_to_one():
    result = SERVICE.predict(_reading())
    probabilities = list(result["condition_probabilities"].values())
    assert sum(probabilities) == pytest.approx(1.0, abs=1e-3)


def test_predictions_are_deterministic():
    first = SERVICE.predict(_reading())
    second = SERVICE.predict(_reading())
    assert first["predicted_power_w"] == second["predicted_power_w"]
    assert first["predicted_condition"] == second["predicted_condition"]


def test_night_reading_gives_no_generation():
    night = SERVICE.predict(_reading(
        solar_voltage=0.0, turbine_rpm=0.0, light_level_lux=0.0,
        light_status="dark", solar_irradiance_wm2=0.0))
    assert night["predicted_power_w"] < 1.0


def test_missing_sensors_are_reported_as_degraded():
    result = SERVICE.predict({
        "reading_timestamp": "2026-03-01T11:00:00+00:00",
        "solar_voltage": 5.0, "wind_voltage": 2.0, "turbine_rpm": 500.0,
    })
    assert "temperature_c" in result["degraded_inputs"]
    assert "humidity_percent" in result["degraded_inputs"]
    assert np.isfinite(result["predicted_power_w"])


def test_threshold_changes_the_anomaly_flag_only():
    low = SERVICE.predict(_reading(), threshold=0.0)
    high = SERVICE.predict(_reading(), threshold=1.0)
    assert low["anomaly_flag"] == 1
    assert high["anomaly_flag"] == 0
    assert low["predicted_power_w"] == high["predicted_power_w"]


def test_predict_series_matches_single_predictions():
    readings = [_reading(), _reading(solar_voltage=0.0, turbine_rpm=0.0,
                                     light_status="dark", light_level_lux=0.0)]
    series = SERVICE.predict_series(readings)
    assert len(series) == 2
    single = SERVICE.predict(readings[0])
    assert series[0]["predicted_power_w"] == single["predicted_power_w"]
    assert series[1]["predicted_power_w"] < 1.0


def test_predict_series_on_empty_list():
    assert SERVICE.predict_series([]) == []


def test_feature_importance_matches_the_training_metrics():
    importance = SERVICE.feature_importance()
    assert importance
    names = [entry["feature"] for entry in importance]
    assert set(names) == set(settings.FEATURE_COLUMNS)
    values = [entry["importance"] for entry in importance]
    assert values == sorted(values, reverse=True)


def test_reading_to_frame_produces_finite_features():
    frame = SERVICE.reading_to_frame(_reading())
    values = frame[settings.FEATURE_COLUMNS].to_numpy(dtype=float)
    assert values.shape == (1, len(settings.FEATURE_COLUMNS))
    assert np.isfinite(values).all()
