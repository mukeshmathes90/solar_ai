"""Train and persist the three microgrid models.

Models
------
1. ``generation_model``  - RandomForestRegressor predicting total estimated
   generation (W) from the live sensor vector.  Used for the short-horizon
   trend/forecast shown on the dashboard.
2. ``condition_model``   - RandomForestClassifier predicting the operating
   condition (normal / reduced_generation / night_idle / fault).
3. ``anomaly_model``     - RandomForestClassifier predicting whether the
   current reading is an injected equipment/sensor anomaly.

Split is chronological (70/15/15).  The validation set is used for model
selection and sanity checks; the test set is touched exactly once, for the
final honest numbers written to ``ml/artifacts/metrics.json``.

Usage
-----
    python -m ml.train
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from ml import preprocess  # noqa: E402
from ml.metrics_util import binary_metrics, classification_metrics, regression_metrics  # noqa: E402

RANDOM_STATE = 42


def _native_classes(model) -> List[object]:
    """``classes_`` holds numpy scalars on Windows; JSON needs native types."""
    out: List[object] = []
    for value in model.classes_:
        if hasattr(value, "item"):
            value = value.item()
        out.append(value)
    return out


def _feature_importance(model, feature_names: List[str]) -> List[Dict[str, object]]:
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        return []
    pairs = sorted(
        zip(feature_names, importances.tolist()),
        key=lambda item: item[1],
        reverse=True,
    )
    return [{"feature": name, "importance": round(float(value), 6)}
            for name, value in pairs]


def train_models(random_state: int = RANDOM_STATE) -> Dict[str, object]:
    """Fit all three models and return metrics plus the fitted estimators."""
    bundle = preprocess.prepare_all()
    train_df, val_df, test_df = bundle["train"], bundle["val"], bundle["test"]
    feature_names = list(settings.FEATURE_COLUMNS)

    results: Dict[str, object] = {
        "feature_columns": feature_names,
        "random_state": random_state,
        "split": {
            "strategy": "chronological_70_15_15",
            "n_train": int(bundle["n_train"]),
            "n_val": int(bundle["n_val"]),
            "n_test": int(bundle["n_test"]),
            "time_range": bundle["time_range"],
            "anomaly_rate": round(float(bundle["anomaly_rate"]), 4),
            "condition_counts": bundle["condition_counts"],
        },
        "models": {},
        "limitations": [
            "Trained on the project dataset; real field accuracy is unknown.",
            "Injected faults are cleanly separable, so the reported F1 overstates "
            "what a noisy field sensor stream would achieve.",
            "Estimated currents come from the same model as the "
            "targets, so the regression task is easier than a real one.",
            "No battery state-of-charge, no cloud forecast and no tariff signal "
            "are modelled; the optimiser is a rule-based demonstration.",
        ],
    }

    trained: Dict[str, object] = {}

    # ------------------------------------------------------------------ #
    # 1. Generation regressor
    # ------------------------------------------------------------------ #
    x_train, y_train, _ = preprocess.matrix(train_df, settings.REGRESSION_TARGET)
    x_val, y_val, _ = preprocess.matrix(val_df, settings.REGRESSION_TARGET)
    x_test, y_test, _ = preprocess.matrix(test_df, settings.REGRESSION_TARGET)

    regressor = RandomForestRegressor(
        n_estimators=220,
        min_samples_leaf=2,
        max_features=0.8,
        random_state=random_state,
        n_jobs=-1,
    )
    start = time.time()
    regressor.fit(x_train, y_train)
    fit_seconds = time.time() - start

    results["models"]["generation"] = {
        "type": "RandomForestRegressor",
        "target": settings.REGRESSION_TARGET,
        "n_estimators": 220,
        "fit_seconds": round(fit_seconds, 2),
        "validation": regression_metrics(y_val, regressor.predict(x_val)),
        "test": regression_metrics(y_test, regressor.predict(x_test)),
        "feature_importance": _feature_importance(regressor, feature_names),
    }
    trained["generation"] = regressor

    # ------------------------------------------------------------------ #
    # 2. Operating-condition classifier
    # ------------------------------------------------------------------ #
    condition_labels = sorted(str(v) for v in bundle["full"][settings.CLASS_TARGET].unique())
    x_train_c, y_train_c, _ = preprocess.matrix(train_df, settings.CLASS_TARGET)
    x_val_c, y_val_c, _ = preprocess.matrix(val_df, settings.CLASS_TARGET)
    x_test_c, y_test_c, _ = preprocess.matrix(test_df, settings.CLASS_TARGET)

    condition_model = RandomForestClassifier(
        n_estimators=220,
        class_weight="balanced_subsample",
        min_samples_leaf=2,
        random_state=random_state,
        n_jobs=-1,
    )
    start = time.time()
    condition_model.fit(x_train_c, y_train_c)
    fit_seconds = time.time() - start

    results["models"]["condition"] = {
        "type": "RandomForestClassifier",
        "target": settings.CLASS_TARGET,
        "classes": _native_classes(condition_model),
        "n_estimators": 220,
        "fit_seconds": round(fit_seconds, 2),
        "validation": classification_metrics(
            y_val_c, condition_model.predict(x_val_c), condition_labels),
        "test": classification_metrics(
            y_test_c, condition_model.predict(x_test_c), condition_labels),
        "feature_importance": _feature_importance(condition_model, feature_names),
    }
    trained["condition"] = condition_model

    # ------------------------------------------------------------------ #
    # 3. Anomaly classifier
    # ------------------------------------------------------------------ #
    x_train_a, y_train_a, _ = preprocess.matrix(train_df, settings.ANOMALY_TARGET)
    x_val_a, y_val_a, _ = preprocess.matrix(val_df, settings.ANOMALY_TARGET)
    x_test_a, y_test_a, _ = preprocess.matrix(test_df, settings.ANOMALY_TARGET)

    anomaly_model = RandomForestClassifier(
        n_estimators=220,
        class_weight="balanced_subsample",
        min_samples_leaf=2,
        random_state=random_state,
        n_jobs=-1,
    )
    start = time.time()
    anomaly_model.fit(x_train_a, y_train_a)
    fit_seconds = time.time() - start

    results["models"]["anomaly"] = {
        "type": "RandomForestClassifier",
        "target": settings.ANOMALY_TARGET,
        "classes": _native_classes(anomaly_model),
        "n_estimators": 220,
        "fit_seconds": round(fit_seconds, 2),
        "validation": binary_metrics(
            y_val_a, anomaly_model.predict(x_val_a)),
        "test": binary_metrics(
            y_test_a, anomaly_model.predict(x_test_a)),
        "feature_importance": _feature_importance(anomaly_model, feature_names),
    }
    trained["anomaly"] = anomaly_model

    return {"bundle": bundle, "results": results, "trained": trained}


def save_artifacts(bundle, results, trained) -> Dict[str, str]:
    """Persist models, feature list and metrics to ml/artifacts/."""
    settings.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump(trained["generation"], settings.GENERATION_MODEL_FILE)
    joblib.dump(trained["condition"], settings.CONDITION_MODEL_FILE)
    joblib.dump(trained["anomaly"], settings.ANOMALY_MODEL_FILE)
    joblib.dump(list(settings.FEATURE_COLUMNS), settings.FEATURE_NAMES_FILE)

    settings.METRICS_FILE.write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    preprocess.write_schema(bundle["full"])

    meta = {
        "model_type_generation": "RandomForestRegressor",
        "model_type_condition": "RandomForestClassifier",
        "model_type_anomaly": "RandomForestClassifier",
        "target_generation": settings.REGRESSION_TARGET,
        "target_condition": settings.CLASS_TARGET,
        "target_anomaly": settings.ANOMALY_TARGET,
        "feature_columns": list(settings.FEATURE_COLUMNS),
        "classes_condition": results["models"]["condition"]["classes"],
        "classes_anomaly": results["models"]["anomaly"]["classes"],
        "model_version": "1.0.0",
        "n_training_rows": int(bundle["n_train"]),
        "n_validation_rows": int(bundle["n_val"]),
        "n_test_rows": int(bundle["n_test"]),
        "anomaly_rate": round(float(bundle["anomaly_rate"]), 4),
        "condition_counts": bundle["condition_counts"],
        "time_range": bundle["time_range"],
        "random_state": int(results["random_state"]),
        "split_strategy": "chronological_70_15_15",
        "trained_at_unix": int(time.time()),
        "data_origin": "simulated",
        "limitations": results["limitations"],
    }
    settings.MODEL_META_FILE.write_text(
        json.dumps(meta, indent=2), encoding="utf-8")

    return {
        "generation": str(settings.GENERATION_MODEL_FILE),
        "condition": str(settings.CONDITION_MODEL_FILE),
        "anomaly": str(settings.ANOMALY_MODEL_FILE),
        "feature_names": str(settings.FEATURE_NAMES_FILE),
        "metrics": str(settings.METRICS_FILE),
        "meta": str(settings.MODEL_META_FILE),
        "schema": str(settings.DATASET_SCHEMA_FILE),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=RANDOM_STATE)
    args = parser.parse_args()

    trained_payload = train_models(random_state=args.seed)
    paths = save_artifacts(
        trained_payload["bundle"],
        trained_payload["results"],
        trained_payload["trained"],
    )

    results = trained_payload["results"]
    print("Artifacts written to %s" % settings.ARTIFACTS_DIR)
    for name, path in paths.items():
        print("  %-14s %s" % (name, path))

    gen = results["models"]["generation"]["test"]
    print("\nGeneration regressor (held-out test set, %d rows)" % gen["n_samples"])
    print("  MAE  = %.4f W" % gen["mae"])
    print("  RMSE = %.4f W" % gen["rmse"])
    print("  R2   = %.4f" % gen["r2"])

    cond = results["models"]["condition"]["test"]
    print("\nOperating-condition classifier (held-out test set, %d rows)"
          % cond["n_samples"])
    print("  accuracy      = %.4f" % cond["accuracy"])
    print("  macro F1      = %.4f" % cond["f1_macro"])
    for label, stats in cond["per_class"].items():
        print("    %-20s P=%.3f R=%.3f F1=%.3f support=%d"
              % (label, stats["precision"], stats["recall"],
                 stats["f1"], stats["support"]))

    anom = results["models"]["anomaly"]["test"]
    print("\nAnomaly classifier (held-out test set, %d rows)" % anom["n_samples"])
    print("  accuracy    = %.4f" % anom["accuracy"])
    print("  precision   = %.4f" % anom["precision"])
    print("  recall      = %.4f" % anom["recall"])
    print("  F1          = %.4f" % anom["f1"])
    print("  confusion   = %s" % (anom["confusion_matrix"],))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
