"""HTTP API behaviour, exercised through the Flask test client."""

from __future__ import annotations

import csv
import io

from backend import db


def _ingest(client, device_token, payload=None, **overrides):
    body = {
        "device_id": "TEST-NODE-01",
        "timestamp": "2026-02-01T09:00:00+00:00",
        "solar_voltage": 5.4,
        "wind_voltage": 2.1,
        "turbine_rpm": 560.0,
        "temperature": 30.0,
        "humidity": 51.0,
        "light_status": "bright",
        "sensor_status": "OK",
        "device_ip": "192.168.43.9",
    }
    if payload is not None:
        body = payload
    body.update(overrides)
    headers = {"X-Device-Token": device_token} if device_token else {}
    return client.post("/api/ingest", json=body, headers=headers)


# --------------------------------------------------------------------------- #
# Envelope / health
# --------------------------------------------------------------------------- #
def test_health_reports_envelope(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["data"]["service"] == "microgrid-ai-api"
    assert "server_time" in body


def test_dashboard_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"<html" in response.data.lower()


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    body = response.get_json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "not_found"


def test_method_not_allowed(client):
    response = client.delete("/api/health")
    assert response.status_code == 405
    assert response.get_json()["error"]["code"] == "method_not_allowed"


def test_empty_database_reports_no_latest(client):
    body = client.get("/api/readings/latest").get_json()
    assert body["data"]["reading"] is None


def test_stats_on_empty_database(client):
    body = client.get("/api/stats").get_json()
    assert body["data"]["total_readings"] == 0


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
def test_ingest_accepts_and_predicted(client, device_token):
    response = _ingest(client, device_token)
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["accepted"] is True
    assert data["reading_id"] is not None
    assert data["reading"]["current_measurable"] is False
    assert data["prediction"] is not None
    assert data["prediction"]["predicted_condition"] in {
        "normal", "reduced_generation", "night_idle", "fault"}
    assert db.reading_count() == 1
    assert len(db.recent_predictions(10)) == 1


def test_ingest_is_idempotent(client, device_token):
    assert _ingest(client, device_token).status_code == 201
    second = _ingest(client, device_token)
    assert second.status_code == 200
    assert second.get_json()["data"]["duplicate"] is True
    assert db.reading_count() == 1


def test_ingest_rejects_without_token(client, device_token):
    if not device_token:
        return
    response = client.post("/api/ingest", json={
        "device_id": "X", "solar_voltage": 5.0, "wind_voltage": 2.0,
        "turbine_rpm": 500.0, "sensor_status": "OK"})
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_ingest_rejects_bad_token(client, device_token):
    if not device_token:
        return
    response = client.post("/api/ingest", json={
        "device_id": "X", "solar_voltage": 5.0, "wind_voltage": 2.0,
        "turbine_rpm": 500.0, "sensor_status": "OK"},
        headers={"X-Device-Token": "definitely-wrong"})
    assert response.status_code == 401


def test_ingest_rejects_invalid_payload(client, device_token):
    response = _ingest(client, device_token, temperature=421.0)
    assert response.status_code == 422
    body = response.get_json()
    assert body["error"]["code"] == "validation_failed"
    assert body["error"]["details"]


def test_ingest_rejects_non_object_body(client, device_token):
    response = client.post("/api/ingest", data="not json",
                           content_type="application/json")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_payload"


def test_ingest_uses_default_device_id_when_absent(client, device_token):
    response = _ingest(client, device_token, payload={
        "timestamp": "2026-02-02T09:00:00+00:00",
        "solar_voltage": 5.0, "wind_voltage": 2.0, "turbine_rpm": 500.0,
        "sensor_status": "OK"})
    assert response.status_code == 201
    stored = db.latest_reading()
    assert stored["device_id"] == db.get_setting("default_device_id", str)


# --------------------------------------------------------------------------- #
# Readings, devices, history
# --------------------------------------------------------------------------- #
def test_latest_and_history_after_ingest(client, device_token):
    _ingest(client, device_token)
    latest = client.get("/api/readings/latest").get_json()["data"]
    assert latest["reading"]["solar_voltage"] == 5.4

    history = client.get("/api/readings/history?hours=all").get_json()
    assert history["meta"]["count"] == 1
    assert history["data"][0]["device_id"] == "TEST-NODE-01"


def test_devices_listed_after_ingest(client, device_token):
    _ingest(client, device_token)
    devices = client.get("/api/devices").get_json()["data"]
    assert len(devices) == 1
    assert devices[0]["device_id"] == "TEST-NODE-01"
    assert devices[0]["online"] == 1


def test_unknown_device_returns_404(client):
    response = client.get("/api/devices/GHOST")
    assert response.status_code == 404


def test_history_rejects_bad_hours(client):
    response = client.get("/api/readings/history?hours=soon")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_parameter"


# --------------------------------------------------------------------------- #
# Prediction routes
# --------------------------------------------------------------------------- #
def test_predict_use_latest_without_data_is_404(client):
    response = client.post("/api/predict", json={"use_latest": True})
    assert response.status_code == 404


def test_predict_use_latest_returns_result(client, device_token):
    _ingest(client, device_token)
    response = client.post("/api/predict", json={"use_latest": True})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "predicted_power_w" in data
    assert 0.0 <= data["anomaly_probability"] <= 1.0


def test_predict_rejects_invalid_input(client):
    response = client.post("/api/predict", json={
        "solar_voltage": 5.0, "wind_voltage": 2.0, "turbine_rpm": 500.0,
        "sensor_status": "OK", "temperature": 500.0})
    assert response.status_code == 422


def test_prediction_series_matches_ingest(client, device_token):
    _ingest(client, device_token)
    series = client.get("/api/predictions/series").get_json()["data"]
    assert len(series) == 1
    assert series[0]["reading_timestamp"] == "2026-02-01T09:00:00+00:00"
    assert series[0]["predicted_power_w"] is not None
    assert series[0]["actual_power_w"] == 0.0


def test_prediction_history_endpoint(client, device_token):
    _ingest(client, device_token)
    rows = client.get("/api/predictions/history").get_json()["data"]
    assert len(rows) == 1
    assert rows[0]["model_version"] is not None


# --------------------------------------------------------------------------- #
# Overview, optimisation, settings
# --------------------------------------------------------------------------- #
def test_overview_shape(client, device_token):
    _ingest(client, device_token)
    data = client.get("/api/overview").get_json()["data"]
    for key in ("reading", "prediction", "device", "devices", "stats",
                "optimization", "settings", "model_ready"):
        assert key in data
    assert data["device_online"] is True
    assert data["settings"]["anomaly_threshold"] == 0.5


def test_overview_without_data_still_works(client):
    data = client.get("/api/overview").get_json()["data"]
    assert data["reading"] is None
    assert data["device_online"] is False
    # No measured generation -> the optimiser must say so, not invent a value.
    assert data["optimization"]["status"] == "unknown"


def test_optimization_is_advisory(client, device_token):
    _ingest(client, device_token)
    data = client.get("/api/optimization").get_json()["data"]
    assert data["status"] in {"surplus", "balanced", "deficit", "unknown"}
    assert set(data["allocation"]) == {
        "critical_load_w", "deferrable_load_w", "storage_charge_w",
        "reserve_held_w", "curtailed_w", "deficit_w"}
    assert data["relay"]["enabled"] is False
    assert data["relay"]["action"] == "hold"
    assert data["recommendations"]


def test_settings_never_leak_the_token(client):
    data = client.get("/api/settings").get_json()["data"]
    assert data["device_token"] in ("", "***")


def test_settings_update_round_trip(client):
    response = client.put("/api/settings", json={"anomaly_threshold": 0.65})
    assert response.status_code == 200
    assert response.get_json()["data"]["anomaly_threshold"] == 0.65
    assert db.get_setting("anomaly_threshold", float) == 0.65


def test_settings_rejects_out_of_range(client):
    response = client.put("/api/settings", json={"anomaly_threshold": 7.0})
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "invalid_settings"


def test_settings_ignores_masked_token_echo(client):
    response = client.put("/api/settings", json={"device_token": "***"})
    assert response.status_code == 200


def test_settings_rejects_non_object(client):
    response = client.put("/api/settings", json=[1, 2, 3])
    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# Model + export + maintenance
# --------------------------------------------------------------------------- #
def test_model_status(client):
    data = client.get("/api/model/status").get_json()["data"]
    assert "ready" in data


def test_model_importance(client):
    data = client.get("/api/model/importance").get_json()["data"]
    assert isinstance(data, (list, dict))


def test_export_csv(client, device_token):
    _ingest(client, device_token)
    response = client.get("/api/export/readings.csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
    assert rows[0][0] == "reading_timestamp"
    assert len(rows) == 2


def test_purge_requires_confirmation(client):
    response = client.post("/api/maintenance/purge", json={})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "confirmation_required"


def test_purge_removes_rows(client, device_token):
    _ingest(client, device_token)
    response = client.post("/api/maintenance/purge", json={"confirm": "DELETE"})
    assert response.status_code == 200
    assert response.get_json()["data"]["removed"] == 1
    assert db.reading_count() == 0


# --------------------------------------------------------------------------- #
# Demo feed (status / seed / tick only - never start the background thread)
# --------------------------------------------------------------------------- #
def test_demo_status(client):
    data = client.get("/api/demo/status").get_json()["data"]
    assert data is not None


def test_demo_seed_marks_simulated(client):
    response = client.post("/api/demo/seed", json={"count": 20, "spacing_seconds": 60})
    assert response.status_code == 200
    assert response.get_json()["data"]["data_origin"] == "simulated"
    assert db.reading_count() > 0
    assert db.stats()["data_origin_counts"].get("simulated", 0) > 0


def test_demo_tick_returns_reading_and_prediction(client):
    data = client.post("/api/demo/tick").get_json()["data"]
    assert data["data_origin"] == "simulated"
    assert data["reading"] is not None
    assert data["prediction"] is not None


def test_demo_tick_twice_in_same_second_is_not_duplicate(client):
    """Rapid ticks must never 503 - timestamps are forced to stay unique."""
    first = client.post("/api/demo/tick")
    second = client.post("/api/demo/tick")
    assert first.status_code == 200
    assert second.status_code == 200
    a = first.get_json()["data"]["reading"]["timestamp"]
    b = second.get_json()["data"]["reading"]["timestamp"]
    assert a != b
    assert db.reading_count() >= 2
