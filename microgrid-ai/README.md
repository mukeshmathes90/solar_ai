# AI-Enabled Predictive Monitoring and Energy Optimization of Renewable Microgrids using IoT

A complete, working mini-project: an ESP8266 sensor node streaming telemetry from
a small hybrid **solar + wind** microgrid, a Flask + SQLite backend that stores
and validates every reading, three scikit-learn models that predict generation,
operating condition and anomalies, and a dark-themed real-time dashboard.

Everything in this repository runs on one laptop. The only hardware dependency
is the ESP8266 node itself; without it the platform runs on a clearly-labelled
simulated feed.

> **Honesty note (please read first).**
> The machine-learning models are trained on a **simulated** dataset, because the
> sensor node is a student prototype, not a metered array. Every simulated value
> is tagged `data_origin = "simulated"` in the database and shown as *simulated*
> on the dashboard. Reported accuracy numbers are real measurements on a
> held-out slice of that simulated data - they are not field accuracy. Sections
> below say exactly which parts are hardware, which are simulated, and which
> cannot be tested without the physical node.

---

## Contents

- [1. What it does](#1-what-it-does)
- [2. Architecture](#2-architecture)
- [3. Quick start](#3-quick-start)
- [4. Manual setup](#4-manual-setup)
- [5. Project structure](#5-project-structure)
- [6. Machine-learning pipeline](#6-machine-learning-pipeline)
- [7. Dashboard](#7-dashboard)
- [8. HTTP API](#8-http-api)
- [9. Firmware and wiring](#9-firmware-and-wiring)
- [10. Live telemetry over a phone hotspot](#10-live-telemetry-over-a-phone-hotspot)
- [11. Tests](#11-tests)
- [12. Data, limits and known constraints](#12-data-limits-and-known-constraints)

---

## 1. What it does

| Capability | Detail |
|---|---|
| **Ingestion** | The node POSTs JSON to `/api/ingest`; the backend validates ranges, deduplicates on `(device_id, timestamp)` and stores the row. |
| **Prediction** | Every stored reading is scored by three models: total generation (W), operating condition (`normal` / `reduced_generation` / `night_idle` / `fault`) and anomaly probability. |
| **Monitoring** | A dashboard auto-refreshes live values, device health, an anomaly gauge and 14 pre-rendered analysis figures. |
| **Optimisation** | A transparent rule-based advisor splits measured generation across essential load, deferrable load and storage. It is **advisory only** - the relay is never switched automatically. |
| **History** | Filterable, paginated data tables plus CSV export. |
| **Fallback** | With no hardware, a simulated feed replays realistic readings so the full pipeline is demonstrable. |

## 2. Architecture

```
   ESP8266 node                     Laptop (all in one process)
 ┌───────────────┐        HTTP      ┌──────────────────────────────────────┐
 │ INA219  x2    │  POST /api/ingest │  Flask  ──►  validation ──►  SQLite  │
 │ DHT11         │ ───────────────►  │    │                          (WAL)  │
 │ KY-024 hall   │    JSON           │    │   ──►  inference (3 models)      │
 │ LDR / relay   │                   │    ▼                          │      │
 └───────────────┘                   │  dashboard (HTML/CSS/JS + Chart.js)  │
        sensors                      └──────────────────────────────────────┘
                                                  browser ▲
```

Data path: **sensors -> ESP8266 -> `/api/ingest` -> SQLite -> models -> dashboard.**
The dashboard is served by the same Flask process and talks to the same
pipeline, so there is no cross-origin setup and no separate front-end build.

## 3. Quick start

The trained models, the seeded dataset and the analysis figures are **committed
to the repository**, so a fresh clone runs without any training step.

```bat
:: 1. install dependencies
python -m pip install -r requirements.txt

:: 2. start the server (opens the firewall, prints the hotspot address)
run.bat
```

Then open <http://127.0.0.1:5000/>. The dashboard is live, the three models are
already loaded, and the demo feed starts automatically - live simulated
readings flow through the whole pipeline immediately.

Use `install.bat` instead of step 1 only when you want to rebuild everything
from scratch (regenerate the dataset, retrain the models, re-render the
figures). It is equivalent to `python scripts/run_pipeline.py`.

## 4. Manual setup

```bat
python -m pip install -r requirements.txt

python -m ml.generate_dataset --rows 12000 --seed 42   :: reproducibility: seed 42
python -m ml.train                                     :: writes ml/artifacts/*
python -m ml.evaluate                                  :: writes reports/graphs/*.png

python -m backend.app                                  :: http://0.0.0.0:5000
python scripts/run_pipeline.py                         :: all three ML stages at once
python -m pytest                                       :: test suite
```

Configuration is read from the environment (see `.env.example`):
`MICROGRID_HOST`, `MICROGRID_PORT`, `MICROGRID_DEBUG`, `MICROGRID_SECRET`,
`MICROGRID_DB`, `MICROGRID_DATASET`. All have working defaults.

## 5. Project structure

```
microgrid-ai/
  backend/
    app.py                 Flask entry point, dashboard + /reports/graphs routes
    db.py                  SQLite schema, dedupe, history, stats, purge
    api/routes.py          every /api/* endpoint
    services/
      validation.py        payload validation + normalisation
      inference.py         loads the 3 models, scores readings
      optimization.py      rule-based energy advisor (advisory only)
      demo_feed.py         simulated feed for hardware-free demos
  config/settings.py       paths, feature list, hardware constants, defaults
  ml/
    generate_dataset.py    simulated dataset generator (seed 42)
    preprocess.py          feature engineering + chronological split
    train.py               fits and persists the three models
    evaluate.py            held-out metrics + report
    graphs.py              the 14 figures
    metrics_util.py        metric helpers
    artifacts/             *.joblib, metrics.json, model_meta.json, schema
  data/
    dataset/microgrid_dataset.csv
    db/microgrid.db
  reports/graphs/          generated PNG figures (+ evaluation_report.md)
  templates/index.html     dashboard
  static/                  css, js (includes Chart.js 4.4.1), img
  firmware/microgrid_node/ ESP8266 sketch + credentials.example.h
  docs/                    WIRING.md, HARDWARE_CHECKLIST.md, LIVE_TELEMETRY.md, TROUBLESHOOTING.md
  scripts/                 diagnose_network.py, backup_csv.py, run_pipeline.py
  tests/                   pytest suite
  install.bat  run.bat  requirements.txt  pytest.ini
```

## 6. Machine-learning pipeline

**Dataset.** `ml/generate_dataset.py` builds a physically plausible time series
for a 6 V / 1.5 W panel, a small DC dynamo, and DHT11 / LDR / hall sensors:
12 000 rows at 5-minute spacing, `seed 42`. It injects labelled faults
(`sensor_fault`, `sensor_stuck`, `generation_drop`, `voltage_rpm_mismatch`,
`overvoltage_spike`) so the anomaly model has something real to learn.

**Split.** Chronological 70 / 15 / 15 - never shuffled, so no future information
leaks into training. The test split is touched exactly once, for the final
numbers.

**Features.** `config/settings.py: FEATURE_COLUMNS` - the raw sensor vector plus
three engineered diagnostics (`solar_v_deficit`, `wind_v_per_rpm`,
`lux_per_irradiance`) that a technician would actually use.

**Models.** `RandomForestRegressor` (generation) and two
`RandomForestClassifier`s (condition, anomaly), 220 trees each.

**Latest held-out results** (1 800 test rows, reproduced by `python -m ml.train`):

| Model | Metric | Value |
|---|---|---|
| Generation | MAE / RMSE / R² | 0.0147 W / 0.0251 W / 0.9968 |
| Condition | accuracy / macro-F1 | 0.8528 / 0.8365 |
| Anomaly | precision / recall / F1 | 0.9636 / 0.8346 / 0.8945 |

These are **simulated-data** numbers - see the note at the top of this file and
the `limitations` list inside `ml/artifacts/metrics.json`. Re-run
`python -m ml.train` any time; the inference service hot-reloads new artifacts
without a server restart.

The live website never contains a hard-coded prediction: every figure on the
dashboard comes from these fitted models.

## 7. Dashboard

Seven sections, all wired to the API:

- **Overview** - KPIs, generation split, latest node reading, device health.
- **Live Monitoring** - per-sensor gauges, the anomaly gauge, a live trend.
- **AI Analytics** - model status, feature importance, the 14 analysis figures.
- **Energy Optimization** - the advisory allocation and its reasoning.
- **Historical Data** - filters, charts, paginated tables, CSV export.
- **Model & System Status** - artifact versions, evaluation metrics, limitations.
- **Settings** - refresh intervals, anomaly threshold, offline window. The Wi-Fi
  password and the device token are never sent to the browser.

Design: deep charcoal background, emerald/amber accents, dark cards, and status
colours (green/amber/red) reused consistently across the UI and the charts.

## 8. HTTP API

All responses use one envelope:
`{"status": "ok", "data": ..., "server_time": ...}` or
`{"status": "error", "error": {"code", "message", "details"}, "server_time"}`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | service health, model readiness, reading count |
| POST | `/api/ingest` | **device endpoint** - validate, store, predict |
| GET | `/api/overview` | one-shot payload for the dashboard |
| GET | `/api/readings/latest` | latest reading (+ prediction) |
| GET | `/api/readings/history` | `hours`, `limit`, `device_id`, `since_unix`, `until_unix` |
| GET | `/api/devices` · `/api/devices/<id>` | device registry and health |
| POST | `/api/predict` | score a payload or `{"use_latest": true}` |
| GET | `/api/predictions/history` · `/api/predictions/series` | stored predictions |
| GET | `/api/optimization` | advisory allocation |
| GET | `/api/stats` | database aggregates |
| GET | `/api/settings` · PUT/POST `/api/settings` | read / update settings |
| GET | `/api/model/status` · `/api/model/importance` | artifact + metric info |
| GET | `/api/export/readings.csv` | CSV download |
| POST | `/api/maintenance/purge` | delete readings (`{"confirm": "DELETE"}`) |
| GET | `/api/demo/status` · POST `/api/demo/start` · `/api/demo/stop` · `/api/demo/seed` · `/api/demo/tick` | simulated feed |
| GET | `/reports/graphs/<file>` | serve a generated figure |

**Ingest contract.** `solar_voltage`, `wind_voltage` and `turbine_rpm` are
required; `temperature`/`humidity`/`light` are accepted as aliases for
`temperature_c`/`humidity_percent`/`light_status`. If `device_token` is set, send
it as `X-Device-Token`. Readings are deduplicated on `(device_id, timestamp)`.
A reading whose current is `null` is stored honestly - power is never fabricated.

## 9. Firmware and wiring

`firmware/microgrid_node/microgrid_node.ino` targets `esp8266:esp8266:nodemcuv2`.
Copy `credentials.example.h` to `credentials.h` and fill in Wi-Fi, backend URL
and (optionally) the device token. Full pin map and power-safety notes are in
`docs/WIRING.md`; `docs/HARDWARE_CHECKLIST.md` is the pre-power checklist.

```bat
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 "firmware\microgrid_node"
```

The sketch samples every 5 s, POSTs JSON, retries Wi-Fi and I2C, keeps the relay
**off**, and emits `null` (not a made-up number) for any current it cannot
measure.

## 10. Live telemetry over a phone hotspot

Phone hotspot -> laptop (Flask) -> dashboard; the ESP8266 only POSTs to the
laptop. Find the laptop's hotspot address with:

```bat
python scripts\diagnose_network.py
```

and paste the printed `#define BACKEND_URL "http://<ip>:5000"` into
`credentials.h`. Full walkthrough, firewall rule and failure table:
`docs/LIVE_TELEMETRY.md`. `run.bat` opens the firewall rule for you.

## 11. Tests

```bat
python -m pytest
```

105 tests cover payload validation, the database layer (including dedupe, purge
and foreign-key correctness), every API route through the Flask test client, the
dataset generator and split, a real model-training run on a small dataset, and
the inference service. Database tests run against a throwaway SQLite file, so
your real `data/db/microgrid.db` is never modified.

## 12. Data, limits and known constraints

Being straight about what this project is:

- **Training data.** The models are trained on the project dataset described in
  the report. Real field accuracy is unknown, and injected faults are cleaner
  than reality, so the reported F1 overstates what a noisy field stream would
  give.
- **Current may be unmeasurable.** With no connected load / closed current path,
  an INA219 reports voltage only. The firmware and backend then store `null`
  current and power rather than inventing values, and the dashboard shows them
  as *unknown*.
- **No battery model.** State of charge is not modelled; the optimiser is a
  documented rule-based demonstration, not a learned optimal controller.
- **Relay is off by default.** Automatic load switching requires a verified
  harness and a low-voltage bench test; it is disabled until an operator enables
  it in Settings.
- **No internet exposure.** The hotspot is a local bridge only - no port
  forwarding, no tunnels, no cloud services.
- **Untested without hardware.** The firmware is compile-verified but has not
  run on a physical node here; anything that needs live sensors is marked as
  such rather than claimed as tested.
