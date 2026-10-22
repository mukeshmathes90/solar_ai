"""Dataset generation, feature engineering and chronological splitting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config import settings
from ml import generate_dataset, preprocess

REQUIRED_COLUMNS = [
    "timestamp", "device_id", "data_origin",
    "solar_voltage", "solar_irradiance_wm2", "wind_voltage", "turbine_rpm",
    "temperature_c", "humidity_percent", "light_level_lux", "wind_speed_ms",
    "soiling_factor", "turbine_efficiency", "clear_sky_power_w",
    "solar_current_est_a", "wind_current_est_a",
    "solar_power_est_w", "wind_power_est_w", "total_est_power_w",
    "operating_condition", "anomaly_label", "anomaly_type",
]


@pytest.fixture(scope="module")
def small_frame():
    return generate_dataset.generate(rows=900, seed=11)


def test_generate_returns_expected_shape(small_frame):
    assert len(small_frame) == 900
    for column in REQUIRED_COLUMNS:
        assert column in small_frame.columns, "missing %s" % column


def test_generate_is_reproducible():
    first = generate_dataset.generate(rows=120, seed=5)
    second = generate_dataset.generate(rows=120, seed=5)
    pd.testing.assert_frame_equal(first, second)


def test_different_seeds_differ():
    first = generate_dataset.generate(rows=120, seed=5)
    second = generate_dataset.generate(rows=120, seed=6)
    assert not first["solar_voltage"].equals(second["solar_voltage"])


def test_no_nulls_in_required_columns(small_frame):
    assert small_frame[REQUIRED_COLUMNS].isna().sum().sum() == 0


def test_timestamps_are_sorted_and_spaced(small_frame):
    stamps = pd.to_datetime(small_frame["timestamp"])
    assert stamps.is_monotonic_increasing
    gaps = stamps.diff().dropna().unique()
    assert len(gaps) == 1


def test_labels_are_from_the_documented_sets(small_frame):
    conditions = set(small_frame["operating_condition"].unique())
    assert conditions <= {"normal", "reduced_generation", "night_idle", "fault"}
    assert set(small_frame["anomaly_label"].unique()) <= {0, 1}
    assert conditions <= set(small_frame["operating_condition"].unique())


def test_night_idle_has_no_sun(small_frame):
    night = small_frame[small_frame["operating_condition"] == "night_idle"]
    if len(night):
        assert night["solar_irradiance_wm2"].max() <= 25.0


def test_anomaly_rate_is_plausible(small_frame):
    rate = small_frame["anomaly_label"].mean()
    assert 0.0 < rate < 0.25


def test_engineer_features_adds_the_expected_columns(small_frame):
    enriched = preprocess.engineer_features(small_frame)
    for column in settings.FEATURE_COLUMNS:
        assert column in enriched.columns, "missing feature %s" % column
    matrix = enriched[settings.FEATURE_COLUMNS].to_numpy(dtype=float)
    assert np.isfinite(matrix).all()


def test_engineered_features_are_deterministic(small_frame):
    first = preprocess.engineer_features(small_frame)
    second = preprocess.engineer_features(small_frame)
    columns = list(settings.FEATURE_COLUMNS)
    pd.testing.assert_frame_equal(first[columns], second[columns])


def test_irradiance_from_lux_zero_in_the_dark():
    assert preprocess.irradiance_from_lux(0.0, "dark") == 0.0


def test_irradiance_from_lux_falls_back_to_status():
    assert 0.0 < preprocess.irradiance_from_lux(None, "bright") <= 1200.0
    assert preprocess.irradiance_from_lux(None, "dark") < 5.0
    assert preprocess.irradiance_from_lux(0.0, "dark") == 0.0


def test_engineered_matrix_variable_is_finite(small_frame):
    enriched = preprocess.engineer_features(small_frame)
    values = enriched[settings.FEATURE_COLUMNS].to_numpy(dtype=float)
    assert np.isfinite(values).all()


def test_chronological_split_sizes(small_frame):
    enriched = preprocess.build_features(small_frame)
    train, val, test = preprocess.chronological_split(enriched)
    total = len(enriched)
    assert len(train) == int(total * 0.70)
    assert len(val) == int(total * 0.85) - int(total * 0.70)
    assert len(train) + len(val) + len(test) == total


def test_split_does_not_leak_across_boundaries(small_frame):
    enriched = preprocess.build_features(small_frame).reset_index(drop=True)
    train, val, test = preprocess.chronological_split(enriched)
    assert train["timestamp"].max() <= val["timestamp"].min()
    assert val["timestamp"].max() <= test["timestamp"].min()


def test_prepare_all_from_file(tmp_path, small_frame):
    csv_path = tmp_path / "small.csv"
    small_frame.to_csv(csv_path, index=False)
    prepared = preprocess.prepare_all(csv_path)
    assert prepared["n_rows"] == 900
    assert prepared["n_train"] + prepared["n_val"] + prepared["n_test"] == 900
    assert prepared["feature_columns"] == list(settings.FEATURE_COLUMNS)
    assert 0.0 < prepared["anomaly_rate"] < 0.25


def test_matrix_returns_numeric_inputs_of_right_width(small_frame):
    x, y, names = preprocess.matrix(small_frame, settings.REGRESSION_TARGET)
    assert x.shape == (len(small_frame), len(settings.FEATURE_COLUMNS))
    assert names == list(settings.FEATURE_COLUMNS)
    assert len(y) == len(small_frame)


def test_matrix_encodes_anomaly_as_int(small_frame):
    _, y, _ = preprocess.matrix(small_frame, settings.ANOMALY_TARGET)
    assert set(np.unique(y)) <= {0, 1}


def test_dataset_schema_reports_targets(small_frame):
    schema = preprocess.dataset_schema(small_frame)
    assert schema["n_rows"] == 900
    assert schema["targets"]["regression"] == settings.REGRESSION_TARGET
