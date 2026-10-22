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
- **Python version matters.** The pinned dependencies (`numpy==1.24.4`,
  `pandas==2.0.3`, `scikit-learn==1.3.2`, `matplotlib==3.7.2`) have no wheels
  for Python 3.12+. Use **Python 3.8 - 3.11** (3.11 recommended).
