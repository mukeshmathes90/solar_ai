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

```bat
cd microgrid-ai
install.bat        :: install dependencies, generate dataset, train models
run.bat            :: start the Flask server (http://127.0.0.1:5000)
```

Then open <http://127.0.0.1:5000/> and press **Start demo feed** to see live
simulated readings flow through the whole pipeline.

```bat
cd microgrid-ai
python -m pytest   :: run the test suite
```

## Notes

- Models are trained on a **simulated** dataset; all simulated rows are tagged
  `data_origin = "simulated"` in the database and labelled as such on the
  dashboard. See the honesty note in `microgrid-ai/README.md`.
- Generated artefacts (trained `*.joblib` models, the SQLite database, the
  dataset CSV and the report figures) are git-ignored. Regenerate them with
  `python scripts/run_pipeline.py`.
- No credentials are committed. Copy `microgrid-ai/.env.example` to `.env` and
  `firmware/microgrid_node/credentials.example.h` to `credentials.h` for local
  secrets.
