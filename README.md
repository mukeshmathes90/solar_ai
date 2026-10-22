# solar_ai

AI-Enabled Predictive Monitoring and Energy Optimization of Renewable Microgrids using IoT.

This repository contains the full mini-project: an ESP8266 sensor node streaming
telemetry from a small hybrid **solar + wind** microgrid, a Flask + SQLite backend
that validates and stores every reading, three scikit-learn models (generation,
operating condition, anomaly), and a dark-themed real-time dashboard.

## Repository layout

| Path | Contents |
|---|---|
| `microgrid-ai/` | The application - backend, ML pipeline, firmware, dashboard, tests, docs. See [`microgrid-ai/README.md`](microgrid-ai/README.md) for the full guide. |
| `report/` | Project report (DOCX/PDF), report builder scripts and diagrams. |
| `laude_final_report/` | Formatted final report copies. |

## Quick start

The repository ships **ready to run**: the trained models, the seeded dataset,
the analysis figures and the demo database are all committed. A fresh clone
needs no training step.

```bat
git clone https://github.com/mukeshmathes90/solar_ai.git
cd solar_ai\microgrid-ai
python -m pip install -r requirements.txt
run.bat            :: starts the server on http://127.0.0.1:5000
```

Then open <http://127.0.0.1:5000/> - the dashboard is live, the models are
loaded and the demo feed starts automatically.

`install.bat` is only needed if you want to rebuild everything from scratch
(fresh dataset, retrain, re-render the figures). It is equivalent to
`python scripts/run_pipeline.py`.

```bat
cd microgrid-ai
python -m pytest   :: run the test suite
```

## Python version

**Python 3.8 - 3.14** are supported. `requirements.txt` uses environment
markers so pip picks the right wheel set for the interpreter it is running
under.

One caveat, handled automatically: scikit-learn model files are not portable
across major scikit-learn releases. The committed artifacts were trained with
scikit-learn 1.3.x, so on **Python 3.12+** (scikit-learn 1.9) `run.bat`
detects that the shipped models cannot score reliably and **retrains them
locally on first start** - about two minutes, no action needed. On Python
3.8 - 3.11 the shipped artifacts are used as-is and start instantly.

## Notes

- Models are trained on a **simulated** dataset; all simulated rows are tagged
  `data_origin = "simulated"` in the database and labelled as such on the
  dashboard. See the honesty note in `microgrid-ai/README.md`.
- The committed artefacts are the exact ones the project was built with:
  `ml/artifacts/*.joblib` (trained models), `ml/artifacts/metrics.json`
  (held-out metrics), `data/dataset/microgrid_dataset.csv` (seed 42),
  `reports/graphs/*.png` (the 14 dashboard figures) and
  `data/db/microgrid.db` (demo history).
- No credentials are committed. Copy `microgrid-ai/.env.example` to `.env` and
  `firmware/microgrid_node/credentials.example.h` to `credentials.h` for local
  secrets.
- **No ESP8266 connected? There is no backend error.** The app starts on the
  built-in simulated feed (`demo_mode = 1`), so the dashboard is live
  immediately with clearly-labelled `SIMULATED` readings. If the feed is
  stopped and no node reports for 90 s, the UI shows an amber
  *"Node is not currently reporting. Showing the last stored reading..."*
  banner. The red **Backend error** banner only appears when an API call
  actually fails (e.g. the server is not running).
- The relay ships **disabled** (`relay_control_enabled = 0`). Automatic load
  switching is never enabled by the shipped data.
