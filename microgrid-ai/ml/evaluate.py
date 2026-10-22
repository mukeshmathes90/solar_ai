"""Re-evaluate the saved models on the held-out test set and write the report.

Run this after :mod:`ml.train`.  It reloads the artifacts from disk, re-runs
inference on the chronological test split that training never fitted on,
recomputes every metric from scratch and regenerates the analysis charts.

Usage
-----
    python -m ml.evaluate
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from ml import graphs, preprocess  # noqa: E402
from ml.metrics_util import binary_metrics, classification_metrics, regression_metrics  # noqa: E402


def load_artifacts() -> Dict[str, object]:
    required = {
        "generation": settings.GENERATION_MODEL_FILE,
        "condition": settings.CONDITION_MODEL_FILE,
        "anomaly": settings.ANOMALY_MODEL_FILE,
        "feature_names": settings.FEATURE_NAMES_FILE,
        "metrics": settings.METRICS_FILE,
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing artifacts: %s. Run `python -m ml.train` first."
            % ", ".join(missing)
        )
    return {
        "generation": joblib.load(settings.GENERATION_MODEL_FILE),
        "condition": joblib.load(settings.CONDITION_MODEL_FILE),
        "anomaly": joblib.load(settings.ANOMALY_MODEL_FILE),
        "feature_names": joblib.load(settings.FEATURE_NAMES_FILE),
        "metrics": json.loads(settings.METRICS_FILE.read_text(encoding="utf-8")),
        "meta": (json.loads(settings.MODEL_META_FILE.read_text(encoding="utf-8"))
                 if settings.MODEL_META_FILE.exists() else {}),
    }


def evaluate(write_graphs: bool = True) -> Dict[str, object]:
    artifacts = load_artifacts()
    bundle = preprocess.prepare_all()
    test_df = bundle["test"]

    x_gen, y_gen, _ = preprocess.matrix(test_df, settings.REGRESSION_TARGET)
    x_cond, y_cond, _ = preprocess.matrix(test_df, settings.CLASS_TARGET)
    x_anom, y_anom, _ = preprocess.matrix(test_df, settings.ANOMALY_TARGET)

    reg_pred = artifacts["generation"].predict(x_gen)
    cond_pred = artifacts["condition"].predict(x_cond)
    anom_pred = artifacts["anomaly"].predict(x_anom)

    condition_labels = sorted(str(v) for v in bundle["full"][settings.CLASS_TARGET].unique())

    report: Dict[str, object] = {
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "split": {
            "strategy": "chronological_70_15_15",
            "n_train": int(bundle["n_train"]),
            "n_val": int(bundle["n_val"]),
            "n_test": int(bundle["n_test"]),
            "time_range": bundle["time_range"],
        },
        "generation": regression_metrics(y_gen, reg_pred),
        "condition": classification_metrics(y_cond, cond_pred, condition_labels),
        "anomaly": binary_metrics(y_anom, anom_pred),
        "trained_metrics_reference": artifacts["metrics"].get("models", {}),
        "model_meta": artifacts["meta"],
        "graph_files": [],
    }

    # Residual detail that only makes sense on the test window.
    residuals = np.asarray(reg_pred, dtype=float) - np.asarray(y_gen, dtype=float)
    within = {
        "within_0.05w": float(np.mean(np.abs(residuals) <= 0.05)),
        "within_0.10w": float(np.mean(np.abs(residuals) <= 0.10)),
        "within_0.25w": float(np.mean(np.abs(residuals) <= 0.25)),
    }
    report["generation"]["tolerance_bands"] = within

    if write_graphs:
        files = graphs.generate_all(
            frame=bundle["full"],
            metrics=artifacts["metrics"],
            y_true_reg=y_gen,
            y_pred_reg=reg_pred,
            times_test=test_df["timestamp"],
            y_true_anom=y_anom,
            y_pred_anom=anom_pred,
            graph_dir=settings.GRAPHS_DIR,
        )
        report["graph_files"] = files

    report_path = settings.REPORTS_DIR / "evaluation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    _write_markdown(report, settings.REPORTS_DIR / "evaluation_report.md")
    return report


def _write_markdown(report: Dict[str, object], path: Path) -> None:
    gen = report["generation"]
    cond = report["condition"]
    anom = report["anomaly"]
    lines = [
        "# Microgrid model evaluation",
        "",
        "Generated %s" % report["evaluated_at"],
        "",
        "> All numbers below are recomputed from predictions on the **held-out",
        "> chronological test set** (`%d` rows) that no model was fitted on."
        % cond["n_samples"],
        "",
        "> The training data is **simulated**. These figures characterise the",
        "> software pipeline, not proven field accuracy on real hardware.",
        "",
        "## 1. Split",
        "",
        "| Split | Rows |",
        "| --- | --- |",
        "| Train | %d |" % report["split"]["n_train"],
        "| Validation | %d |" % report["split"]["n_val"],
        "| Test | %d |" % report["split"]["n_test"],
        "",
        "Strategy: %s" % report["split"]["strategy"],
        "",
        "## 2. Generation regressor (RandomForestRegressor)",
        "",
        "Target: total estimated power (W)",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        "| MAE | %.4f W |" % gen["mae"],
        "| RMSE | %.4f W |" % gen["rmse"],
        "| R2 | %.4f |" % gen["r2"],
        "| Max absolute error | %.4f W |" % gen["max_abs_error"],
        "",
        "Fraction of predictions inside a tolerance band:",
        "",
        "| Band | Share |",
        "| --- | --- |",
        "| +/- 0.05 W | %.1f%% |" % (100.0 * gen["tolerance_bands"]["within_0.05w"]),
        "| +/- 0.10 W | %.1f%% |" % (100.0 * gen["tolerance_bands"]["within_0.10w"]),
        "| +/- 0.25 W | %.1f%% |" % (100.0 * gen["tolerance_bands"]["within_0.25w"]),
        "",
        "## 3. Operating-condition classifier (RandomForestClassifier)",
        "",
        "Target: `normal` / `reduced_generation` / `night_idle` / `fault`",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        "| Accuracy | %.4f |" % cond["accuracy"],
        "| Macro precision | %.4f |" % cond["precision_macro"],
        "| Macro recall | %.4f |" % cond["recall_macro"],
        "| Macro F1 | %.4f |" % cond["f1_macro"],
        "",
        "Per class:",
        "",
        "| Class | Precision | Recall | F1 | Support |",
        "| --- | --- | --- | --- | --- |",
    ]
    for label, stats in cond["per_class"].items():
        lines.append("| %s | %.3f | %.3f | %.3f | %d |"
                     % (label, stats["precision"], stats["recall"],
                        stats["f1"], stats["support"]))

    lines += [
        "",
        "Confusion matrix (rows = actual, columns = predicted):",
        "",
        "```",
        "                predicted",
        "actual   " + "  ".join("%14s" % str(c) for c in cond["labels"]),
    ]
    for label, row in zip(cond["labels"], cond["confusion_matrix"]):
        lines.append("%-14s" % str(label) + "  ".join("%14d" % v for v in row))
    lines += [
        "```",
        "",
        "## 4. Anomaly detector (RandomForestClassifier)",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        "| Accuracy | %.4f |" % anom["accuracy"],
        "| Precision | %.4f |" % anom["precision"],
        "| Recall | %.4f |" % anom["recall"],
        "| F1 | %.4f |" % anom["f1"],
        "| Specificity | %.4f |" % anom["specificity"],
        "",
        "| | Count |",
        "| --- | --- |",
        "| True positives | %d |" % anom["true_positive"],
        "| False positives | %d |" % anom["false_positive"],
        "| False negatives | %d |" % anom["false_negative"],
        "| True negatives | %d |" % anom["true_negative"],
        "",
        "## 5. Limitations",
        "",
    ]
    for item in report.get("model_meta", {}).get("limitations", []):
        lines.append("- %s" % item)
    lines += [
        "",
        "## 6. Charts",
        "",
    ]
    for name in sorted(Path(p).name for p in report.get("graph_files", [])):
        lines.append("- `%s`" % name)
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-graphs", action="store_true")
    args = parser.parse_args()

    report = evaluate(write_graphs=not args.no_graphs)

    gen = report["generation"]
    cond = report["condition"]
    anom = report["anomaly"]

    print("Evaluation written to %s" % (settings.REPORTS_DIR / "evaluation_report.md"))
    print("\nHeld-out test set: %d rows" % cond["n_samples"])
    print("  Generation MAE  = %.4f W" % gen["mae"])
    print("  Generation RMSE = %.4f W" % gen["rmse"])
    print("  Generation R2   = %.4f" % gen["r2"])
    print("  Condition acc   = %.4f  macro F1 = %.4f"
          % (cond["accuracy"], cond["f1_macro"]))
    print("  Anomaly  F1     = %.4f  precision = %.4f  recall = %.4f"
          % (anom["f1"], anom["precision"], anom["recall"]))
    if report["graph_files"]:
        print("\nCharts written:")
        for path in report["graph_files"]:
            print("  %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
