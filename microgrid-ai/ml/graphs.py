"""Static analysis charts written to ``reports/graphs``.

Chart style matches the dashboard palette (charcoal canvas, emerald primary,
amber secondary) so the figures in the report read as one document with the
web UI.  Every figure is saved as a PNG *and* returned so the same code can be
reused for live dashboard tiles.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import confusion_matrix  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402

BG = "#0E1116"
PANEL = "#161B22"
GRID = "#2A323C"
TEXT = "#E6EDF3"
MUTED = "#8B949E"
GREEN = "#2ECC71"
AMBER = "#F5A623"
RED = "#FF5C5C"
BLUE = "#5AA9E6"
PURPLE = "#A78BFA"

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": PANEL,
    "savefig.facecolor": BG,
    "text.color": TEXT,
    "axes.labelcolor": TEXT,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.edgecolor": GRID,
    "axes.titlecolor": TEXT,
    "grid.color": GRID,
    "grid.linewidth": 0.7,
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "figure.dpi": 130,
})

GENERATED_FILES: List[str] = []


def _finish(fig, name: str, graph_dir: Path) -> Path:
    graph_dir.mkdir(parents=True, exist_ok=True)
    path = graph_dir / name
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=BG)
    plt.close(fig)
    GENERATED_FILES.append(str(path))
    return path


def _thin_time_axis(ax) -> None:
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
    ax.tick_params(axis="x", rotation=0)


def chart_solar_over_time(frame: pd.DataFrame, graph_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(11, 4.6))
    sample = frame.iloc[:: max(1, len(frame) // 900)]
    ax.plot(sample["timestamp"], sample["solar_voltage"], color=GREEN,
            linewidth=1.5, label="Solar voltage (V)")
    ax.set_ylabel("Voltage (V)", color=GREEN)
    ax.tick_params(axis="y", labelcolor=GREEN)
    ax.grid(True, alpha=0.35)

    ax2 = ax.twinx()
    ax2.plot(sample["timestamp"], sample["solar_power_est_w"], color=AMBER,
             linewidth=1.4, alpha=0.9, label="Estimated solar power (W)")
    ax2.set_ylabel("Power (W)", color=AMBER)
    ax2.tick_params(axis="y", labelcolor=AMBER)
    ax2.set_facecolor(PANEL)

    _thin_time_axis(ax)
    ax.set_title("Solar array voltage and estimated power over time")
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [line.get_label() for line in lines], loc="upper right",
              framealpha=0.85, facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT)
    return _finish(fig, "solar_voltage_power_over_time.png", graph_dir)


def chart_wind_over_time(frame: pd.DataFrame, graph_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(11, 4.6))
    sample = frame.iloc[:: max(1, len(frame) // 900)]
    ax.plot(sample["timestamp"], sample["wind_voltage"], color=GREEN,
            linewidth=1.5, label="Dynamo voltage (V)")
    ax.set_ylabel("Voltage (V)", color=GREEN)
    ax.tick_params(axis="y", labelcolor=GREEN)
    ax.grid(True, alpha=0.35)

    ax2 = ax.twinx()
    ax2.plot(sample["timestamp"], sample["turbine_rpm"], color=BLUE,
             linewidth=1.2, alpha=0.9, label="Turbine RPM")
    ax2.set_ylabel("RPM", color=BLUE)
    ax2.tick_params(axis="y", labelcolor=BLUE)
    ax2.set_facecolor(PANEL)

    _thin_time_axis(ax)
    ax.set_title("Wind dynamo voltage and turbine speed over time")
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [line.get_label() for line in lines], loc="upper right",
              framealpha=0.85, facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT)
    return _finish(fig, "wind_voltage_rpm_over_time.png", graph_dir)


def chart_light_vs_solar(frame: pd.DataFrame, graph_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    sample = frame.iloc[:: max(1, len(frame) // 2500)]
    scatter = ax.scatter(
        sample["light_level_lux"],
        sample["solar_power_est_w"],
        c=sample["solar_irradiance_wm2"],
        cmap="viridis", s=9, alpha=0.65, linewidths=0,
    )
    ax.set_xlabel("Light level (lux)")
    ax.set_ylabel("Estimated solar power (W)")
    ax.set_title("Illuminance vs solar generation")
    ax.grid(True, alpha=0.35)
    bar = fig.colorbar(scatter, ax=ax)
    bar.set_label("Irradiance (W/m2)", color=MUTED)
    bar.ax.yaxis.set_tick_params(color=MUTED)
    plt.setp(plt.getp(bar.ax.axes, "yticklabels"), color=MUTED)
    return _finish(fig, "light_vs_solar_generation.png", graph_dir)


def chart_rpm_vs_wind(frame: pd.DataFrame, graph_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    sample = frame.iloc[:: max(1, len(frame) // 2500)]
    scatter = ax.scatter(
        sample["turbine_rpm"],
        sample["wind_power_est_w"],
        c=sample["wind_voltage"],
        cmap="plasma", s=9, alpha=0.65, linewidths=0,
    )
    ax.set_xlabel("Turbine speed (RPM)")
    ax.set_ylabel("Estimated wind power (W)")
    ax.set_title("Turbine RPM vs wind generation")
    ax.grid(True, alpha=0.35)
    bar = fig.colorbar(scatter, ax=ax)
    bar.set_label("Dynamo voltage (V)", color=MUTED)
    bar.ax.yaxis.set_tick_params(color=MUTED)
    plt.setp(plt.getp(bar.ax.axes, "yticklabels"), color=MUTED)
    return _finish(fig, "rpm_vs_wind_generation.png", graph_dir)


def chart_source_contribution(frame: pd.DataFrame, graph_dir: Path) -> Path:
    sample = frame.iloc[:: max(1, len(frame) // 600)]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.stackplot(
        sample["timestamp"],
        sample["solar_power_est_w"],
        sample["wind_power_est_w"],
        labels=["Solar", "Wind"],
        colors=[GREEN, AMBER],
        alpha=0.88,
    )
    ax.set_ylabel("Estimated power (W)")
    ax.set_title("Solar vs wind contribution to total generation")
    ax.grid(True, alpha=0.35)
    _thin_time_axis(ax)
    ax.legend(loc="upper right", framealpha=0.85, facecolor=PANEL,
              edgecolor=GRID, labelcolor=TEXT)

    solar_mean = float(frame["solar_power_est_w"].mean())
    wind_mean = float(frame["wind_power_est_w"].mean())
    ax.text(
        0.012, 0.94,
        "Mean share: solar %.1f%% / wind %.1f%%"
        % (100.0 * solar_mean / (solar_mean + wind_mean + 1e-9),
           100.0 * wind_mean / (solar_mean + wind_mean + 1e-9)),
        transform=ax.transAxes, va="top", ha="left", color=TEXT,
        bbox=dict(boxstyle="round,pad=0.4", facecolor=PANEL, edgecolor=GRID),
    )
    return _finish(fig, "solar_vs_wind_contribution.png", graph_dir)


def chart_condition_breakdown(frame: pd.DataFrame, graph_dir: Path) -> Path:
    counts = frame["operating_condition"].value_counts()
    order = [c for c in ["normal", "reduced_generation", "night_idle", "fault"]
             if c in counts.index]
    colours = {"normal": GREEN, "reduced_generation": AMBER,
               "night_idle": BLUE, "fault": RED}

    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    bars = ax.bar(
        [c.replace("_", " ") for c in order],
        [int(counts[c]) for c in order],
        color=[colours[c] for c in order],
        edgecolor=GRID,
        width=0.62,
    )
    total = int(counts.sum())
    for bar, label in zip(bars, order):
        value = int(counts[label])
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + total * 0.012,
                "%d\n(%.1f%%)" % (value, 100.0 * value / total),
                ha="center", va="bottom", color=TEXT, fontsize=9)
    ax.set_ylabel("Samples")
    ax.set_title("Operating-condition distribution across the dataset")
    ax.grid(True, axis="y", alpha=0.35)
    ax.set_ylim(0, max(int(counts.max()) * 1.18, 1))
    return _finish(fig, "operating_condition_distribution.png", graph_dir)


def chart_normal_vs_anomaly(frame: pd.DataFrame, graph_dir: Path) -> Path:
    sample = frame.iloc[:: max(1, len(frame) // 2000)]
    fig, ax = plt.subplots(figsize=(10.4, 4.8))

    normal = sample[sample["anomaly_label"] == 0]
    anomaly = sample[sample["anomaly_label"] == 1]

    ax.scatter(normal["hour"], normal["total_est_power_w"], s=6,
               color=GREEN, alpha=0.35, label="Normal", linewidths=0)
    ax.scatter(anomaly["hour"], anomaly["total_est_power_w"], s=22,
               color=RED, alpha=0.9, label="Anomalous", linewidths=0,
               marker="x")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Total estimated power (W)")
    ax.set_title("Normal vs anomalous operating patterns")
    ax.grid(True, alpha=0.35)
    ax.legend(loc="upper right", framealpha=0.85, facecolor=PANEL,
              edgecolor=GRID, labelcolor=TEXT)

    rates = frame.groupby("anomaly_type")["anomaly_label"].mean()
    detail = ", ".join(
        "%s %.0f%%" % (name, 100.0 * float(value))
        for name, value in rates.items() if name != "none"
    )
    ax.text(0.012, 0.94, "Injected fault mix: %s" % detail,
            transform=ax.transAxes, va="top", ha="left", color=TEXT, fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.35", facecolor=PANEL, edgecolor=GRID))
    return _finish(fig, "normal_vs_anomalous_patterns.png", graph_dir)


def chart_feature_importance(metrics: Dict[str, object], graph_dir: Path) -> Path:
    importance = metrics["models"]["generation"]["feature_importance"]
    names = [item["feature"] for item in importance][::-1]
    values = [item["importance"] for item in importance][::-1]

    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    colours = [GREEN if i >= len(values) - 3 else "#3D4A5C" for i in range(len(values))]
    ax.barh(names, values, color=colours, edgecolor=GRID, height=0.66)
    ax.set_xlabel("Mean decrease in impurity (importance)")
    ax.set_title("Feature importance - generation regressor")
    ax.grid(True, axis="x", alpha=0.35)
    for index, value in enumerate(values):
        ax.text(value + max(values) * 0.012, index, "%.3f" % value,
                va="center", color=MUTED, fontsize=8.5)
    ax.set_xlim(0, max(values) * 1.16)
    return _finish(fig, "feature_importance.png", graph_dir)


def chart_regression_evaluation(y_true, y_pred, graph_dir: Path) -> Path:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    residuals = y_pred - y_true

    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.8))

    axes[0].scatter(y_true, y_pred, s=8, color=GREEN, alpha=0.45, linewidths=0)
    limit = float(max(y_true.max(), y_pred.max())) * 1.06 + 1e-6
    axes[0].plot([0, limit], [0, limit], color=AMBER, linewidth=1.4,
                 linestyle="--", label="Ideal y = x")
    axes[0].set_xlabel("Actual estimated power (W)")
    axes[0].set_ylabel("Predicted power (W)")
    axes[0].set_title("Regression evaluation - parity plot")
    axes[0].set_xlim(0, limit)
    axes[0].set_ylim(0, limit)
    axes[0].grid(True, alpha=0.35)
    axes[0].legend(framealpha=0.85, facecolor=PANEL, edgecolor=GRID,
                   labelcolor=TEXT)

    axes[1].hist(residuals, bins=42, color=BLUE, edgecolor=GRID, alpha=0.9)
    axes[1].axvline(0.0, color=AMBER, linewidth=1.4, linestyle="--")
    axes[1].set_xlabel("Prediction error (W)")
    axes[1].set_ylabel("Count")
    axes[1].set_title("Error distribution (residuals)")
    axes[1].grid(True, alpha=0.35)
    axes[1].text(
        0.97, 0.93,
        "mean %.4f W\nstd  %.4f W" % (float(residuals.mean()),
                                      float(residuals.std())),
        transform=axes[1].transAxes, ha="right", va="top", color=TEXT,
        fontsize=9, bbox=dict(boxstyle="round,pad=0.35", facecolor=PANEL,
                              edgecolor=GRID),
    )
    return _finish(fig, "regression_evaluation.png", graph_dir)


def chart_confusion(matrix, labels, title: str, name: str,
                    graph_dir: Path, cmap: str = "Greens") -> Path:
    matrix = np.asarray(matrix, dtype=int)
    fig, ax = plt.subplots(figsize=(7.4, 5.6))
    image = ax.imshow(matrix, cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels([str(label).replace("_", "\n") for label in labels], fontsize=8.5)
    ax.set_yticklabels([str(label).replace("_", "\n") for label in labels], fontsize=8.5)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)

    threshold = matrix.max() * 0.62 if matrix.max() else 0
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            value = int(matrix[row, col])
            ax.text(col, row, str(value), ha="center", va="center",
                    color=BG if value > threshold else TEXT, fontsize=11,
                    fontweight="bold")
    bar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    bar.ax.yaxis.set_tick_params(color=MUTED)
    plt.setp(plt.getp(bar.ax.axes, "yticklabels"), color=MUTED)
    return _finish(fig, name, graph_dir)


def chart_actual_vs_predicted(times, y_true, y_pred, graph_dir: Path) -> Path:
    times = pd.to_datetime(pd.Series(list(times)))
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    fig, ax = plt.subplots(figsize=(11.4, 4.8))
    ax.plot(times, y_true, color=GREEN, linewidth=1.5, label="Actual (held-out test)")
    ax.plot(times, y_pred, color=AMBER, linewidth=1.4, linestyle="--",
            label="Model prediction")
    ax.fill_between(times, y_true, y_pred, color=RED, alpha=0.16,
                    label="Absolute error")
    ax.set_xlabel("Time")
    ax.set_ylabel("Total estimated power (W)")
    ax.set_title("Actual vs predicted generation on the held-out test set")
    ax.grid(True, alpha=0.35)
    _thin_time_axis(ax)
    ax.legend(loc="upper right", framealpha=0.85, facecolor=PANEL,
              edgecolor=GRID, labelcolor=TEXT)
    return _finish(fig, "actual_vs_predicted_heldout.png", graph_dir)


def chart_generation_trend_forecast(times, y_true, y_pred,
                                    graph_dir: Path,
                                    horizon: int = 24) -> Path:
    """Recent held-out history plus a naive persistence forecast."""
    times = pd.to_datetime(pd.Series(list(times)))
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    tail = min(len(times), 260)
    window_t = times.iloc[-tail:] if hasattr(times, "iloc") else times[-tail:]
    window_true = y_true[-tail:]
    window_pred = y_pred[-tail:]

    step = float(np.median(np.diff(window_t.values).astype("timedelta64[s]").astype(float))) \
        if tail > 1 else 300.0
    last_time = window_t.iloc[-1] if hasattr(window_t, "iloc") else window_t[-1]
    future_t = pd.to_datetime(
        [last_time + pd.Timedelta(seconds=step * (i + 1)) for i in range(horizon)]
    )
    last_value = float(window_pred[-1])
    # Damped persistence: keeps the last prediction but decays toward the
    # recent mean, which is an honest baseline rather than a fake curve.
    recent_mean = float(np.mean(window_true[-48:])) if len(window_true) else last_value
    decay = np.power(0.94, np.arange(1, horizon + 1))
    future_y = recent_mean + (last_value - recent_mean) * decay

    fig, ax = plt.subplots(figsize=(11.4, 4.8))
    ax.plot(window_t, window_true, color=GREEN, linewidth=1.5, label="Actual")
    ax.plot(window_t, window_pred, color=AMBER, linewidth=1.4, linestyle="--",
            label="Predicted")
    ax.plot(future_t, future_y, color=PURPLE, linewidth=1.6, linestyle=":",
            label="Damped persistence forecast (%d steps)" % horizon)
    ax.axvspan(window_t.iloc[-1] if hasattr(window_t, "iloc") else window_t[-1],
               future_t[-1], color=PURPLE, alpha=0.10)
    ax.set_xlabel("Time")
    ax.set_ylabel("Total estimated power (W)")
    ax.set_title("Generation trend and short-horizon forecast")
    ax.grid(True, alpha=0.35)
    _thin_time_axis(ax)
    ax.legend(loc="upper right", framealpha=0.85, facecolor=PANEL,
              edgecolor=GRID, labelcolor=TEXT)
    return _finish(fig, "generation_trend_forecast.png", graph_dir)


def chart_model_comparison(metrics: Dict[str, object], graph_dir: Path) -> Path:
    cond = metrics["models"]["condition"]["test"]
    anom = metrics["models"]["anomaly"]["test"]
    labels = list(cond["labels"])
    scores = [cond["per_class"][label]["f1"] for label in labels]
    colours = [GREEN, AMBER, BLUE, RED]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))

    axes[0].bar([label.replace("_", "\n") for label in labels], scores,
                color=colours[:len(labels)], edgecolor=GRID, width=0.6)
    axes[0].set_ylim(0, 1.08)
    axes[0].set_ylabel("F1 score")
    axes[0].set_title("Operating-condition F1 by class (held-out test)")
    axes[0].grid(True, axis="y", alpha=0.35)
    for index, score in enumerate(scores):
        axes[0].text(index, score + 0.02, "%.2f" % score, ha="center",
                     color=TEXT, fontsize=9)

    bars = axes[1].bar(
        ["Precision", "Recall", "F1"],
        [anom["precision"], anom["recall"], anom["f1"]],
        color=[GREEN, AMBER, BLUE], edgecolor=GRID, width=0.55,
    )
    axes[1].set_ylim(0, 1.08)
    axes[1].set_title("Anomaly detector scores (held-out test)")
    axes[1].grid(True, axis="y", alpha=0.35)
    for bar, value in zip(bars, [anom["precision"], anom["recall"], anom["f1"]]):
        axes[1].text(bar.get_x() + bar.get_width() / 2, value + 0.02,
                     "%.2f" % value, ha="center", color=TEXT, fontsize=9)
    return _finish(fig, "model_score_comparison.png", graph_dir)


def generate_all(frame, metrics, y_true_reg, y_pred_reg, times_test,
                 y_true_anom, y_pred_anom,
                 graph_dir: Optional[Path] = None) -> List[str]:
    """Produce every chart the report and dashboard reference."""
    target = Path(graph_dir) if graph_dir else settings.GRAPHS_DIR
    target.mkdir(parents=True, exist_ok=True)
    GENERATED_FILES.clear()

    chart_solar_over_time(frame, target)
    chart_wind_over_time(frame, target)
    chart_light_vs_solar(frame, target)
    chart_rpm_vs_wind(frame, target)
    chart_source_contribution(frame, target)
    chart_condition_breakdown(frame, target)
    chart_normal_vs_anomaly(frame, target)
    chart_feature_importance(metrics, target)
    chart_regression_evaluation(y_true_reg, y_pred_reg, target)
    chart_confusion(
        metrics["models"]["condition"]["test"]["confusion_matrix"],
        metrics["models"]["condition"]["test"]["labels"],
        "Confusion matrix - operating condition (held-out test)",
        "confusion_matrix_condition.png", target, cmap="Greens")
    chart_confusion(
        metrics["models"]["anomaly"]["test"]["confusion_matrix"],
        metrics["models"]["anomaly"]["test"]["labels"],
        "Confusion matrix - anomaly detector (held-out test)",
        "confusion_matrix_anomaly.png", target, cmap="Oranges")
    chart_actual_vs_predicted(times_test, y_true_reg, y_pred_reg, target)
    chart_generation_trend_forecast(times_test, y_true_reg, y_pred_reg, target)
    chart_model_comparison(metrics, target)

    return list(GENERATED_FILES)
