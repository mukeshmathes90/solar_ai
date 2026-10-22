"""HTTP API for the microgrid platform.

Consistent envelope
-------------------
Success::

    { "status": "ok", "data": <payload>, "server_time": "<iso>" }

Failure::

    { "status": "error", "error": { "code": "...", "message": "...",
                                    "details": [...] }, "server_time": "..." }

Every payload keeps three things visibly separate:

* ``data_origin = "hardware"``   - a real device POST
* ``data_origin = "simulated"``  - replayed training data
* ``prediction`` fields          - model output, never a measurement
"""

from __future__ import annotations

import csv
import io
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, Response, jsonify, request

from backend import db
from backend.services import demo_feed, inference, optimization, validation
from config import settings

api = Blueprint("api", __name__, url_prefix="/api")


# --------------------------------------------------------------------------- #
# Envelope helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ok(data: Any, status: int = 200, **meta: Any) -> Tuple[Response, int]:
    body: Dict[str, Any] = {"status": "ok", "data": data, "server_time": _now_iso()}
    if meta:
        body["meta"] = meta
    return jsonify(body), status


def err(message: str, code: str = "bad_request", status: int = 400,
        details: Optional[List[str]] = None) -> Tuple[Response, int]:
    body = {
        "status": "error",
        "error": {"code": code, "message": message,
                  "details": details or []},
        "server_time": _now_iso(),
    }
    return jsonify(body), status


def _options() -> Dict[str, Any]:
    """Current persisted settings as native types, plus derived flags."""
    stored = db.get_settings()
    options: Dict[str, Any] = {}
    for key, caster in settings.SETTING_TYPES.items():
        try:
            options[key] = caster(stored.get(key))
        except (TypeError, ValueError):
            options[key] = settings.DEFAULT_SETTINGS.get(key)
    return options


# --------------------------------------------------------------------------- #
# Health / status
# --------------------------------------------------------------------------- #
@api.get("/health")
def health():
    ready = inference.SERVICE.is_ready()
    return ok({
        "service": "microgrid-ai-api",
        "status": "healthy" if ready else "degraded",
        "models_ready": ready,
        "inference_error": inference.SERVICE.status().get("last_error"),
        "readings": db.reading_count(),
        "database": str(db.db_path()),
        "demo_feed": demo_feed.FEED.status(),
        "seconds_up": round(time.monotonic(), 1),
    })


@api.get("/model/status")
def model_status():
    return ok(inference.SERVICE.status())


@api.get("/model/importance")
def model_importance():
    return ok(inference.SERVICE.feature_importance())


@api.get("/stats")
def stats():
    return ok(db.stats())


@api.get("/settings")
def get_settings_route():
    options = _options()
    # Never leak the device token or a stored Wi-Fi secret to the browser.
    options["device_token"] = "***" if options.get("device_token") else ""
    return ok(options)


@api.put("/settings")
@api.post("/settings")
def update_settings_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return err("Settings payload must be a JSON object.", "invalid_payload")
    if "device_token" in payload and payload["device_token"] == "***":
        payload.pop("device_token")
    _, rejected = db.set_settings(payload)
    if rejected:
        return err("Some settings were rejected.", "invalid_settings", 422, rejected)
    # Return the same native types GET /api/settings uses (not raw DB strings).
    options = _options()
    options["device_token"] = "***" if options.get("device_token") else ""
    return ok(options)


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
def _check_device_token(payload: Dict[str, Any]) -> Optional[Tuple[Response, int]]:
    expected = db.get_setting("device_token", str) or ""
    if not expected:
        return None
    supplied = request.headers.get("X-Device-Token") or payload.get("device_token")
    if not supplied or str(supplied) != expected:
        return err("Invalid or missing device token.", "unauthorized", 401)
    return None


@api.post("/ingest")
def ingest():
    """Main device endpoint. Validates, stores, then predicts."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return err("Request body must be a JSON object.", "invalid_payload", 400,
                   ["The ESP8266 firmware posts application/json."])

    unauthorized = _check_device_token(payload)
    if unauthorized:
        return unauthorized

    row, errors = validation.validate_payload(payload)
    if errors or row is None:
        return err("Reading rejected by validation.", "validation_failed", 422, errors)

    if not row.get("device_id"):
        row["device_id"] = db.get_setting("default_device_id", str) or "ESP8266-GRID-01"
    row["data_origin"] = "hardware"

    try:
        inserted, row_id = db.insert_reading(row)
    except Exception as exc:
        return err("Database write failed: %s" % exc, "storage_error", 500)

    if not inserted:
        return ok({
            "accepted": False,
            "duplicate": True,
            "message": "Reading already stored (same device_id and timestamp).",
        }, 200)

    db.touch_device(row["device_id"], row.get("device_ip"), row.get("sensor_status"))
    stored = db.latest_reading(row["device_id"])

    prediction: Optional[Dict[str, Any]] = None
    prediction_error: Optional[str] = None
    try:
        prediction = inference.SERVICE.predict(
            stored, threshold=float(db.get_setting("anomaly_threshold", float)))
        db.insert_prediction(row_id, row["device_id"], prediction)
    except Exception as exc:
        prediction_error = str(exc)

    return ok({
        "accepted": True,
        "duplicate": False,
        "reading_id": row_id,
        "reading": validation.summarise_reading(stored),
        "prediction": prediction,
        "prediction_error": prediction_error,
    }, 201)


# --------------------------------------------------------------------------- #
# Readings
# --------------------------------------------------------------------------- #
@api.get("/readings/latest")
def latest_reading():
    device_id = request.args.get("device_id")
    record = db.latest_reading(device_id)
    if not record:
        return ok({"reading": None, "prediction": None, "device": None},
                  200, note="no readings stored yet")

    offline_after = int(db.get_setting("device_offline_after_s", int))
    device = db.device_status(record["device_id"], offline_after)

    prediction: Optional[Dict[str, Any]] = None
    try:
        prediction = inference.SERVICE.predict(
            record, threshold=float(db.get_setting("anomaly_threshold", float)))
    except Exception as exc:
        prediction = {"error": str(exc)}

    return ok({
        "reading": validation.summarise_reading(record),
        "raw": _public_reading(record),
        "prediction": prediction,
        "device": device,
    })


def _public_reading(record: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(record)
    out.pop("raw_json", None)
    return out


@api.get("/readings/history")
def readings_history():
    def _int_arg(name: str, default: int) -> int:
        try:
            return int(request.args.get(name, default))
        except (TypeError, ValueError):
            return default

    hours_arg = request.args.get("hours")
    hours: Optional[float] = None
    if hours_arg not in (None, "", "all"):
        try:
            hours = max(0.001, float(hours_arg))
        except ValueError:
            return err("hours must be a number.", "invalid_parameter")

    limit = _int_arg("limit", 500)
    since = request.args.get("since_unix")
    until = request.args.get("until_unix")
    try:
        since_unix = int(since) if since not in (None, "") else None
        until_unix = int(until) if until not in (None, "") else None
    except ValueError:
        return err("since_unix/until_unix must be integers.", "invalid_parameter")

    rows = db.history(hours=hours, limit=limit, since_unix=since_unix,
                      until_unix=until_unix, device_id=request.args.get("device_id"))
    rows = list(reversed(rows))  # ascending for charts
    points = [validation.summarise_reading(row) for row in rows]
    return ok(points, 200, count=len(points),
              origin_breakdown=_origin_breakdown(rows))


def _origin_breakdown(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        origin = row.get("data_origin") or "unknown"
        counts[origin] = counts.get(origin, 0) + 1
    return counts


@api.get("/devices")
def devices():
    offline_after = int(db.get_setting("device_offline_after_s", int))
    return ok(db.list_devices(offline_after))


@api.get("/devices/<device_id>")
def device(device_id: str):
    offline_after = int(db.get_setting("device_offline_after_s", int))
    record = db.device_status(device_id, offline_after)
    if not record:
        return err("Unknown device.", "not_found", 404)
    return ok(record)


# --------------------------------------------------------------------------- #
# Prediction
# --------------------------------------------------------------------------- #
@api.post("/predict")
def predict():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return err("Request body must be a JSON object.", "invalid_payload")
    try:
        threshold = float(payload.get("anomaly_threshold",
                                      db.get_setting("anomaly_threshold", float)))
    except (TypeError, ValueError):
        threshold = float(db.get_setting("anomaly_threshold", float))

    if not inference.SERVICE.is_ready():
        return err("Models are not trained yet. Run `python -m ml.train`.",
                   "model_unavailable", 503)

    if payload.get("use_latest"):
        record = db.latest_reading(payload.get("device_id"))
        if not record:
            return err("No readings stored yet.", "not_found", 404)
        source = validation.summarise_reading(record)
    else:
        row, errors = validation.validate_payload(payload)
        if errors or row is None:
            return err("Prediction input failed validation.", "validation_failed",
                       422, errors)
        source = validation.summarise_reading(row)

    try:
        result = inference.SERVICE.predict(source, threshold=threshold)
    except Exception as exc:
        return err("Inference failed: %s" % exc, "inference_error", 500)
    return ok(result)


@api.get("/predictions/history")
def predictions_history():
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    return ok(db.recent_predictions(limit))


@api.get("/predictions/series")
def predictions_series():
    """Predictions joined to their source reading, oldest-first for charts."""
    try:
        limit = int(request.args.get("limit", 300))
    except (TypeError, ValueError):
        limit = 300
    return ok(list(reversed(db.prediction_series(limit))))


# --------------------------------------------------------------------------- #
# Dashboard aggregate + optimisation
# --------------------------------------------------------------------------- #
@api.get("/overview")
def overview():
    options = _options()
    offline_after = int(options.get("device_offline_after_s", 90))

    devices = db.list_devices(offline_after)
    latest = db.latest_reading()
    reading_view = validation.summarise_reading(latest) if latest else None

    prediction = None
    if latest:
        try:
            prediction = inference.SERVICE.predict(
                latest, threshold=float(options.get("anomaly_threshold", 0.5)))
        except Exception as exc:
            prediction = {"error": str(exc)}

    device_online = False
    device_record = None
    if latest:
        device_record = db.device_status(latest["device_id"], offline_after)
        device_online = bool(device_record and device_record["online"])

    generation = None
    if reading_view and reading_view.get("total_est_power_w") is not None:
        generation = reading_view["total_est_power_w"]

    optimised = optimization.optimise_energy(reading_view, {
        "optimize_load_low_w": options.get("optimize_load_low_w", 1.5),
        "optimize_load_high_w": options.get("optimize_load_high_w", 4.0),
        "optimize_reserve_w": options.get("optimize_reserve_w", 5.0),
        "device_online": device_online,
        "relay_control_enabled": options.get("relay_control_enabled", 0),
        "generation_w": generation,
        "predicted_generation_w": (prediction or {}).get("predicted_power_w"),
        "device_online_seconds": (device_record or {}).get("seconds_since_last_seen"),
    })

    return ok({
        "reading": reading_view,
        "raw": _public_reading(latest) if latest else None,
        "prediction": prediction,
        "device": device_record,
        "devices": devices,
        "device_online": device_online,
        "stats": db.stats(),
        "optimization": optimised,
        "settings": {
            "dashboard_refresh_s": options.get("dashboard_refresh_s", 5),
            "sampling_interval_s": options.get("sampling_interval_s", 5),
            "anomaly_threshold": options.get("anomaly_threshold", 0.5),
            "demo_mode": options.get("demo_mode", 1),
            "device_offline_after_s": offline_after,
            "history_window_h": options.get("history_window_h", 24),
        },
        "model_ready": inference.SERVICE.is_ready(),
        "demo_feed": demo_feed.FEED.status(),
    })


@api.get("/optimization")
def optimization_route():
    return _optimization_payload()


def _optimization_payload():
    options = _options()
    offline_after = int(options.get("device_offline_after_s", 90))
    latest = db.latest_reading()
    reading_view = validation.summarise_reading(latest) if latest else None
    device_record = (db.device_status(latest["device_id"], offline_after)
                     if latest else None)
    generation = reading_view.get("total_est_power_w") if reading_view else None

    prediction = None
    if latest:
        try:
            prediction = inference.SERVICE.predict(
                latest, threshold=float(options.get("anomaly_threshold", 0.5)))
        except Exception:
            prediction = None

    result = optimization.optimise_energy(reading_view, {
        "optimize_load_low_w": options.get("optimize_load_low_w", 1.5),
        "optimize_load_high_w": options.get("optimize_load_high_w", 4.0),
        "optimize_reserve_w": options.get("optimize_reserve_w", 5.0),
        "device_online": bool(device_record and device_record["online"]),
        "relay_control_enabled": options.get("relay_control_enabled", 0),
        "generation_w": generation,
        "predicted_generation_w": (prediction or {}).get("predicted_power_w"),
        "device_online_seconds": (device_record or {}).get("seconds_since_last_seen"),
    })
    return ok(result)


# --------------------------------------------------------------------------- #
# Export / maintenance
# --------------------------------------------------------------------------- #
@api.get("/export/readings.csv")
def export_readings():
    columns, table = db.export_csv()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(table)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=microgrid_readings_%s.csv" % stamp
        },
    )


@api.post("/maintenance/purge")
def purge():
    payload = request.get_json(silent=True) or {}
    if payload.get("confirm") != "DELETE":
        return err("Set \"confirm\": \"DELETE\" to purge stored readings.",
                   "confirmation_required", 400)
    days = payload.get("older_than_days")
    if days is None:
        removed = db.purge_all_readings()
        return ok({"removed": removed, "scope": "all"})
    try:
        days = float(days)
    except (TypeError, ValueError):
        return err("older_than_days must be a number.", "invalid_parameter")
    cutoff = int(time.time() - max(0.0, days) * 86400)
    removed = db.purge_readings(cutoff)
    return ok({"removed": removed, "scope": "before_unix", "cutoff_unix": cutoff})


# --------------------------------------------------------------------------- #
# Demo feed
# --------------------------------------------------------------------------- #
@api.get("/demo/status")
def demo_status():
    return ok(demo_feed.FEED.status())


@api.post("/demo/start")
def demo_start():
    db.set_settings({"demo_mode": 1})
    demo_feed.FEED.start()
    return ok(demo_feed.FEED.status())


@api.post("/demo/stop")
def demo_stop():
    db.set_settings({"demo_mode": 0})
    return ok(demo_feed.FEED.status())


@api.post("/demo/seed")
def demo_seed():
    payload = request.get_json(silent=True) or {}
    try:
        count = int(payload.get("count", 240))
        spacing = int(payload.get("spacing_seconds", 300))
    except (TypeError, ValueError):
        return err("count and spacing_seconds must be integers.", "invalid_parameter")
    result = demo_feed.FEED.seed(count=count, spacing_seconds=spacing)
    return ok({
        "inserted": result["inserted"],
        "skipped": result["skipped"],
        "count": count,
        "spacing_seconds": spacing,
        "data_origin": "simulated",
    })


@api.post("/demo/tick")
def demo_tick():
    reading = demo_feed.FEED.tick()
    if not reading:
        return err("Demo feed could not produce a reading.", "demo_unavailable", 503)
    prediction = None
    try:
        prediction = inference.SERVICE.predict(
            reading, threshold=float(db.get_setting("anomaly_threshold", float)))
        db.insert_prediction(reading.get("id"), reading.get("device_id"), prediction)
    except Exception:
        prediction = None
    return ok({
        "reading": validation.summarise_reading(reading),
        "prediction": prediction,
        "data_origin": "simulated",
    })
