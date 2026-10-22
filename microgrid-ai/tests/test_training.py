"""Training pipeline: real fits on a small simulated dataset."""

from __future__ import annotations

import json

import joblib
import numpy as np
import pytest

from config import settings
from ml import generate_dataset, preprocess, train


@pytest.fixture(scope="module")
def small_dataset(tmp_path_factory):
    path = tmp_path_factory.mktemp("ml-data") / "tiny.csv"
    generate_dataset.generate(rows=900, seed=21).to_csv(path, index=False)
    return path


@pytest.fixture()
def trained(small_dataset, monkeypatch):
    monkeypatch.setattr(settings, "DATASET_PATH", small_dataset)
    return train.train_models(random_state=7)


def test_results_have_the_expected_structure(trained):
    results = trained["results"]
    assert results["feature_columns"] == list(settings.FEATURE_COLUMNS)
    assert set(results["models"]) == {"generation", "condition", "anomaly"}
    assert results["split"]["strategy"] == "chronological_70_15_15"
    assert results["split"]["n_train"] + results["split"]["n_val"] \
        + results["split"]["n_test"] == 900
    assert results["limitations"]


def test_test_split_is_used_exactly_once_for_final_numbers(trained):
    results = trained["results"]
    for name in ("generation", "condition", "anomaly"):
        assert "validation" in results["models"][name]
        assert "test" in results["models"][name]
        assert results["models"][name]["test"]["n_samples"] == 135


def test_regression_metrics_are_sane(trained):
    test_metrics = trained["results"]["models"]["generation"]["test"]
    assert test_metrics["mae"] >= 0.0
    assert test_metrics["rmse"] >= test_metrics["mae"] - 1e-9
    assert -1.0 <= test_metrics["r2"] <= 1.0


def test_condition_model_exposes_all_documented_classes(trained):
    classes = trained["results"]["models"]["condition"]["classes"]
    assert set(classes) <= {"normal", "reduced_generation", "night_idle", "fault"}
    assert "normal" in classes
    for label, stats in trained["results"]["models"]["condition"]["test"]["per_class"].items():
        assert stats["support"] >= 0
        assert label in classes


def test_anomaly_metrics_have_binary_shape(trained):
    metrics = trained["results"]["models"]["anomaly"]["test"]
    for key in ("accuracy", "precision", "recall", "f1"):
        assert 0.0 <= metrics[key] <= 1.0
    assert np.array(metrics["confusion_matrix"]).shape == (2, 2)


def test_feature_importance_is_sorted_and_complete(trained):
    importance = trained["results"]["models"]["generation"]["feature_importance"]
    names = [entry["feature"] for entry in importance]
    assert set(names) == set(settings.FEATURE_COLUMNS)
    values = [entry["importance"] for entry in importance]
    assert values == sorted(values, reverse=True)
    assert sum(values) == pytest.approx(1.0, abs=1e-3)


def test_trained_models_predict_the_right_shapes(trained):
    bundle = trained["bundle"]
    features, _, _ = preprocess.matrix(bundle["test"], settings.REGRESSION_TARGET)
    trained_models = trained["trained"]
    assert trained_models["generation"].predict(features[:10]).shape == (10,)
    assert trained_models["condition"].predict(features[:10]).shape == (10,)
    assert trained_models["anomaly"].predict(features[:10]).shape == (10,)


def test_training_is_reproducible(small_dataset, monkeypatch):
    monkeypatch.setattr(settings, "DATASET_PATH", small_dataset)
    first = train.train_models(random_state=3)["results"]["models"]["generation"]["test"]
    second = train.train_models(random_state=3)["results"]["models"]["generation"]["test"]
    assert first["r2"] == pytest.approx(second["r2"], abs=1e-9)


def test_save_artifacts_writes_loadable_files(trained, tmp_path, monkeypatch):
    for attribute in ("ARTIFACTS_DIR", "GENERATION_MODEL_FILE", "CONDITION_MODEL_FILE",
                      "ANOMALY_MODEL_FILE", "FEATURE_NAMES_FILE", "METRICS_FILE",
                      "MODEL_META_FILE", "DATASET_SCHEMA_FILE"):
        original = getattr(settings, attribute)
        name = original.name if hasattr(original, "name") else attribute
        monkeypatch.setattr(settings, attribute, tmp_path / name)

    paths = train.save_artifacts(trained["bundle"], trained["results"],
                                 trained["trained"])
    for path in paths.values():
        assert path and json_ok_or_loadable(path)

    reloaded = joblib.load(settings.GENERATION_MODEL_FILE)
    features, _, _ = preprocess.matrix(trained["bundle"]["test"], settings.REGRESSION_TARGET)
    assert reloaded.predict(features[:3]).shape == (3,)

    metrics = json.loads(settings.METRICS_FILE.read_text(encoding="utf-8"))
    assert "models" in metrics

    meta = json.loads(settings.MODEL_META_FILE.read_text(encoding="utf-8"))
    assert meta["data_origin"] == "simulated"
    assert meta["model_version"] == "1.0.0"
    assert meta["feature_columns"] == list(settings.FEATURE_COLUMNS)


def json_ok_or_loadable(path: str) -> bool:
    from pathlib import Path
    candidate = Path(path)
    if not candidate.exists():
        return False
    if candidate.suffix == ".json":
        json.loads(candidate.read_text(encoding="utf-8"))
    return True
