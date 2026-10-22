"""Metric helpers shared by training and evaluation.

Every number produced here is computed from real held-out predictions.  Nothing
is rounded up, interpolated or hard-coded.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    r2_score,
)


def regression_metrics(y_true, y_pred) -> Dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mse = float(mean_squared_error(y_true, y_pred))
    return {
        "n_samples": int(len(y_true)),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mse)),
        "mse": mse,
        "r2": float(r2_score(y_true, y_pred)),
        "max_abs_error": float(np.max(np.abs(y_true - y_pred))),
        "mean_actual": float(np.mean(y_true)),
        "mean_predicted": float(np.mean(y_pred)),
    }


def classification_metrics(y_true, y_pred, labels: List[str]) -> Dict[str, object]:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    matrix = confusion_matrix(y_true, y_pred, labels=labels)

    per_class: Dict[str, Dict[str, float]] = {}
    for index, label in enumerate(labels):
        tp = float(matrix[index][index])
        fp = float(matrix[:, index].sum() - tp)
        fn = float(matrix[index, :].sum() - tp)
        tn = float(matrix.sum() - tp - fp - fn)
        support = int(matrix[index, :].sum())
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) else 0.0)
        per_class[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": support,
            "true_positive": int(tp),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_negative": int(tn),
        }

    return {
        "n_samples": int(len(y_true)),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision_macro": round(
            float(precision_score(y_true, y_pred, average="macro",
                                  labels=labels, zero_division=0)), 4),
        "recall_macro": round(
            float(recall_score(y_true, y_pred, average="macro",
                               labels=labels, zero_division=0)), 4),
        "f1_macro": round(
            float(f1_score(y_true, y_pred, average="macro",
                           labels=labels, zero_division=0)), 4),
        "f1_weighted": round(
            float(f1_score(y_true, y_pred, average="weighted",
                           labels=labels, zero_division=0)), 4),
        "labels": list(labels),
        "confusion_matrix": matrix.astype(int).tolist(),
        "per_class": per_class,
    }


def binary_metrics(y_true, y_pred, positive_label=1) -> Dict[str, object]:
    """Precision / recall / F1 for the anomaly detector (positive = anomaly)."""
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    matrix = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = (int(v) for v in matrix.ravel())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    return {
        "n_samples": int(len(y_true)),
        "positive_label": int(positive_label),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "specificity": round(float(specificity), 4),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "labels": [0, 1],
        "confusion_matrix": matrix.astype(int).tolist(),
    }
