"""SQLite persistence: dedupe, history, stats, settings and purge."""

from __future__ import annotations

import time

from backend import db


def _row(timestamp, device_id="DEV-1", origin="hardware", solar_v=5.0, wind_v=2.0):
    return {
        "device_id": device_id,
        "reading_timestamp": timestamp,
        "data_origin": origin,
        "solar_voltage": solar_v,
        "solar_current": None,
        "solar_power": None,
        "wind_voltage": wind_v,
        "wind_current": None,
        "wind_power": None,
        "turbine_rpm": 480.0,
        "temperature_c": 28.0,
        "humidity_percent": 55.0,
        "light_status": "bright",
        "light_level_lux": None,
        "sensor_status": "OK",
        "device_ip": "192.168.43.37",
        "raw_json": None,
    }


def test_insert_returns_true_then_deduplicates(temp_db):
    assert db.insert_reading(_row("2026-01-01T00:00:00+00:00"))[0] is True
    inserted, row_id = db.insert_reading(_row("2026-01-01T00:00:00+00:00"))
    assert inserted is False
    assert row_id is None
    assert db.reading_count() == 1


def test_same_timestamp_different_device_is_allowed(temp_db):
    db.insert_reading(_row("2026-01-01T00:00:00+00:00", device_id="A"))
    db.insert_reading(_row("2026-01-01T00:00:00+00:00", device_id="B"))
    assert db.reading_count() == 2


def test_latest_reading_returns_newest(temp_db):
    db.insert_reading(_row("2026-01-01T00:00:00+00:00", solar_v=1.0))
    db.insert_reading(_row("2026-01-01T01:00:00+00:00", solar_v=9.0))
    latest = db.latest_reading()
    assert latest is not None
    assert latest["solar_voltage"] == 9.0


def test_history_filters_by_device(temp_db):
    db.insert_reading(_row("2026-01-01T00:00:00+00:00", device_id="A"))
    db.insert_reading(_row("2026-01-01T00:00:00+00:00", device_id="B"))
    rows = db.history(device_id="A")
    assert len(rows) == 1
    assert rows[0]["device_id"] == "A"


def test_history_respects_limit(temp_db):
    for index in range(5):
        db.insert_reading(_row("2026-01-01T0%d:00:00+00:00" % index))
    assert len(db.history(limit=3)) == 3


def test_stats_reports_counts_and_aggregates(temp_db):
    db.insert_reading(_row("2026-01-01T00:00:00+00:00", solar_v=4.0))
    db.insert_reading(_row("2026-01-01T01:00:00+00:00", origin="simulated", solar_v=6.0))
    stats = db.stats()
    assert stats["total_readings"] == 2
    assert stats["data_origin_counts"]["hardware"] == 1
    assert stats["data_origin_counts"]["simulated"] == 1
    assert stats["aggregates"]["solar_voltage"]["min"] == 4.0
    assert stats["aggregates"]["solar_voltage"]["max"] == 6.0


def test_settings_bounds_are_enforced(temp_db):
    _, rejected = db.set_settings({"anomaly_threshold": 5.0})
    assert rejected
    assert db.get_setting("anomaly_threshold", float) == 0.5


def test_settings_unknown_key_is_rejected(temp_db):
    _, rejected = db.set_settings({"not_a_setting": 1})
    assert rejected


def test_settings_round_trip(temp_db):
    db.set_settings({"anomaly_threshold": 0.7, "default_device_id": "NODE-9"})
    assert db.get_setting("anomaly_threshold", float) == 0.7
    assert db.get_setting("default_device_id", str) == "NODE-9"


def test_touch_device_marks_online(temp_db):
    db.insert_reading(_row("2026-01-01T00:00:00+00:00"))
    db.touch_device("DEV-1", "192.168.43.37", "OK")
    devices = db.list_devices(offline_after_s=90)
    assert len(devices) == 1
    assert devices[0]["online"] == 1
    assert devices[0]["device_id"] == "DEV-1"


def test_device_offline_when_stale(temp_db):
    db.insert_reading(_row("2026-01-01T00:00:00+00:00"))
    db.touch_device("DEV-1", None, "OK")
    # Backdate the device heartbeat to simulate a node that went quiet.
    connection = db.connect()
    connection.execute(
        "UPDATE devices SET last_seen_unix = ? WHERE device_id = ?",
        (int(time.time()) - 3600, "DEV-1"),
    )
    connection.commit()
    devices = db.list_devices(offline_after_s=90)
    assert devices[0]["online"] == 0


def test_purge_all_readings(temp_db):
    db.insert_reading(_row("2026-01-01T00:00:00+00:00"))
    db.insert_reading(_row("2026-01-01T01:00:00+00:00"))
    removed = db.purge_all_readings()
    assert removed == 2
    assert db.reading_count() == 0


def test_prediction_series_joins_reading(temp_db):
    inserted, row_id = db.insert_reading(_row("2026-01-01T00:00:00+00:00"))
    assert inserted
    db.insert_prediction(row_id, "DEV-1", {
        "predicted_power_w": 3.21,
        "predicted_condition": "normal",
        "anomaly_probability": 0.04,
        "anomaly_flag": 0,
        "model_version": "1.0.0",
        "features": {},
    })
    series = db.prediction_series(limit=10)
    assert len(series) == 1
    entry = series[0]
    assert entry["predicted_power_w"] == 3.21
    assert entry["actual_power_w"] == 0.0
    assert entry["reading_timestamp"] == "2026-01-01T00:00:00+00:00"


def test_export_csv_has_expected_columns(temp_db):
    db.insert_reading(_row("2026-01-01T00:00:00+00:00"))
    columns, table = db.export_csv()
    assert "reading_timestamp" in columns
    assert "solar_voltage" in columns
    assert len(table) == 1


def test_purge_readings_before_cutoff(temp_db):
    db.insert_reading(_row("2026-01-01T00:00:00+00:00"))
    removed = db.purge_readings(int(time.time() + 3600))
    assert removed == 1
