"""Generate the three explanatory diagrams used by the mini-project report.

White background, black text, Times New Roman - print friendly. Run as part of
``build_report.py``; can also be executed on its own.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402

plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "DejaVu Serif"]
plt.rcParams["savefig.dpi"] = 200

OUT = Path(r"D:\viyaltech\Project_shop_phase_17072026\Vivekandha_solar\report\diagrams")

GREEN = "#E8F5E9"
AMBER = "#FFF4E0"
GREY = "#F0F0F0"
BLUE = "#E8F0FA"


def box(ax, x, y, w, h, lines, face=GREY, fontsize=8, bold_first=True, edge="black"):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=face, edgecolor=edge, lw=1.0))
    lines = [lines] if isinstance(lines, str) else list(lines)
    n = len(lines)
    step = h / (n + 1)
    for index, text in enumerate(lines):
        ax.text(x + w / 2.0, y + h - step * (index + 1), text, ha="center", va="center",
                fontsize=fontsize, fontweight=("bold" if (bold_first and index == 0) else "normal"))


def arrow(ax, x1, y1, x2, y2, label=None, style="-|>", dashed=False):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                                 mutation_scale=11, lw=1.0, color="black",
                                 linestyle=("--" if dashed else "-"),
                                 shrinkA=0, shrinkB=0))
    if label:
        ax.text((x1 + x2) / 2.0, (y1 + y2) / 2.0 + 1.6, label, ha="center",
                va="bottom", fontsize=7)


def _canvas():
    fig, ax = plt.subplots(figsize=(9.0, 5.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    return fig, ax


def architecture():
    fig, ax = _canvas()
    ax.text(50, 96, "Sensor Node", ha="center", fontsize=9, fontweight="bold")
    ax.text(78, 96, "Server (laptop)", ha="center", fontsize=9, fontweight="bold")

    sensors = [
        ["Solar panel (6 V)", "+ INA219 sensor"],
        ["Wind dynamo", "+ INA219 sensor"],
        ["DHT11", "temperature / humidity"],
        ["LDR module", "light level"],
        ["KY-024 Hall", "rotor speed"],
    ]
    y = 76.0
    for lines in sensors:
        box(ax, 2, y, 26, 12.5, lines, face=GREEN, fontsize=7.5)
        y -= 15.0

    box(ax, 32, 40, 24, 24, ["ESP8266 NodeMCU", "embedded firmware", "5 s sampling", "JSON over Wi-Fi"],
        face=AMBER, fontsize=8)
    arrow(ax, 28, 62, 32, 58, "analogue /", style="-|>")
    ax.text(30, 57, "digital pins", ha="center", fontsize=6.5)

    box(ax, 62, 76, 36, 13, ["Flask REST API", "/api/ingest  (validation + dedupe)"],
        face=BLUE, fontsize=8)
    arrow(ax, 56, 62, 62, 80, "Wi-Fi 2.4 GHz\nHTTP POST (JSON)")

    box(ax, 62, 55, 36, 12, ["SQLite database", "(readings, devices, predictions, settings)"],
        face=GREY, fontsize=7.5)
    box(ax, 62, 34, 36, 12, ["ML inference service", "(generation, condition, anomaly models)"],
        face=GREY, fontsize=7.5)
    box(ax, 62, 13, 36, 12, ["Web dashboard + advisory optimiser", "(Chart.js, live refresh)"],
        face=GREY, fontsize=7.5)

    arrow(ax, 80, 76, 80, 67)
    arrow(ax, 80, 55, 80, 46)
    arrow(ax, 80, 34, 80, 25)

    fig.savefig(str(OUT / "report_architecture.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def data_flow():
    fig, ax = _canvas()
    ax.text(50, 93, "Online pipeline (live telemetry)", ha="center", fontsize=9, fontweight="bold")
    online = ["Acquire", "Validate", "Store", "Predict", "Visualise", "Advise"]
    xs = [1, 17.6, 34.2, 50.8, 67.4, 84]
    for x, label in zip(xs, online):
        box(ax, x, 68, 14, 14, label, face=BLUE, fontsize=8, bold_first=True)
    for index in range(len(xs) - 1):
        arrow(ax, xs[index] + 14, 75, xs[index + 1], 75)

    ax.text(50, 55, "Offline pipeline (model development)", ha="center", fontsize=9, fontweight="bold")
    offline = ["Generate\ndataset", "Engineer\nfeatures", "Train\nmodels", "Evaluate", "Report\nfigures"]
    oxs = [5, 24, 43, 62, 81]
    for x, label in zip(oxs, offline):
        box(ax, x, 26, 16, 16, label.split("\n"), face=AMBER, fontsize=8, bold_first=False)
    for index in range(len(oxs) - 1):
        arrow(ax, oxs[index] + 16, 34, oxs[index + 1], 34)

    arrow(ax, 51, 42, 57.8, 68, "model artifacts (.joblib)", dashed=True)
    ax.text(50, 8, "The same feature engineering and hardware constants are shared by both pipelines.",
            ha="center", fontsize=7.5, style="italic")

    fig.savefig(str(OUT / "report_dataflow.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def entity_relationship():
    fig, ax = _canvas()
    box(ax, 2, 12, 30, 78, [
        "readings",
        "id (PK)",
        "device_id",
        "reading_timestamp",
        "received_at_unix",
        "data_origin",
        "solar_voltage / current / power",
        "wind_voltage / current / power",
        "turbine_rpm",
        "temperature_c / humidity_percent",
        "light_status / light_level_lux",
        "sensor_status / device_ip",
        "UNIQUE(device_id, reading_timestamp)",
    ], face=GREEN, fontsize=6.6)

    box(ax, 36, 58, 28, 32, [
        "devices",
        "device_id (PK)",
        "first_seen_unix",
        "last_seen_unix",
        "last_ip",
        "last_sensor_status",
        "total_readings",
    ], face=BLUE, fontsize=6.8)

    box(ax, 36, 12, 28, 32, [
        "settings",
        "key (PK)",
        "value",
        "updated_at_unix",
    ], face=AMBER, fontsize=6.8)

    box(ax, 68, 12, 30, 78, [
        "predictions",
        "id (PK)",
        "reading_id (FK)",
        "device_id",
        "predicted_at_unix",
        "predicted_power_w",
        "predicted_condition",
        "anomaly_probability",
        "anomaly_flag",
        "model_version",
        "features_json",
    ], face=GREY, fontsize=6.6)

    arrow(ax, 68, 50, 32, 50, "references", style="-|>")
    arrow(ax, 64, 74, 32, 74, "one reading", style="-|>", dashed=True)
    arrow(ax, 64, 28, 32, 28, "device metadata", style="-|>", dashed=True)

    fig.savefig(str(OUT / "report_er.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    architecture()
    data_flow()
    entity_relationship()
    for name in ("report_architecture.png", "report_dataflow.png", "report_er.png"):
        print("wrote", OUT / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
