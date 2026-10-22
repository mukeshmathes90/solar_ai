"""SQLite persistence for readings, devices, settings and predictions.

Design notes
------------
* The database file is created automatically on first use, so a fresh clone
  only needs ``pip install -r requirements.txt`` plus ``python -m backend.app``.
* Readings are deduplicated on ``(device_id, reading_timestamp)``.  An ESP8266
  that reconnects and re-POSTs the same sample therefore cannot pollute the
  history or inflate any statistic.
* ``solar_current`` / ``wind_current`` are allowed to be ``NULL``.  A node with
  no connected load cannot measure generated current through an INA219, and
  inventing a value would be dishonest, so the schema simply accepts "unknown".
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from config import settings

_LOCK = threading.RLock()
_CONNECTION: Optional[sqlite3.Connection] = None

READING_COLUMNS = [
    "device_id",
    "reading_timestamp",
    "data_origin",
    "solar_voltage",
    "solar_current",
    "solar_power",
    "wind_voltage",
    "wind_current",
    "wind_power",
    "turbine_rpm",
    "temperature_c",
    "humidity_percent",
    "light_status",
    "light_level_lux",
    "sensor_status",
    "device_ip",
    "raw_json",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id          TEXT    NOT NULL,
    reading_timestamp  TEXT    NOT NULL,
    received_at_unix   INTEGER NOT NULL,
    data_origin        TEXT    NOT NULL DEFAULT 'hardware',
    solar_voltage      REAL,
    solar_current      REAL,
    solar_power        REAL,
    wind_voltage       REAL,
    wind_current       REAL,
    wind_power         REAL,
    turbine_rpm        REAL,
    temperature_c      REAL,
    humidity_percent   REAL,
    light_status       TEXT,
    light_level_lux    REAL,
    sensor_status      TEXT,
    device_ip          TEXT,
    raw_json           TEXT,
    UNIQUE (device_id, reading_timestamp)
);
CREATE INDEX IF NOT EXISTS idx_readings_ts        ON readings (reading_timestamp);
CREATE INDEX IF NOT EXISTS idx_readings_device_ts ON readings (device_id, reading_timestamp);
CREATE INDEX IF NOT EXISTS idx_readings_received  ON readings (received_at_unix);

CREATE TABLE IF NOT EXISTS devices (
    device_id          TEXT    PRIMARY KEY,
    first_seen_unix    INTEGER NOT NULL,
    last_seen_unix     INTEGER NOT NULL,
    last_ip            TEXT,
    last_sensor_status TEXT,
    total_readings     INTEGER NOT NULL DEFAULT 0,
    notes              TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key              TEXT PRIMARY KEY,
    value            TEXT NOT NULL,
    updated_at_unix  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    reading_id           INTEGER,
    device_id            TEXT,
    predicted_at_unix    INTEGER NOT NULL,
    predicted_power_w    REAL,
    predicted_condition  TEXT,
    anomaly_probability  REAL,
    anomaly_flag         INTEGER,
    model_version        TEXT,
    features_json        TEXT,
    FOREIGN KEY (reading_id) REFERENCES readings (id)
);
CREATE INDEX IF NOT EXISTS idx_predictions_ts ON predictions (predicted_at_unix);
"""


# --------------------------------------------------------------------------- #
# Connection handling
# --------------------------------------------------------------------------- #
def db_path() -> Path:
    return Path(settings.DATABASE_PATH)


def connect() -> sqlite3.Connection:
    """Return the shared connection, creating schema on first use."""
    global _CONNECTION
    with _LOCK:
        if _CONNECTION is None:
            path = db_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                str(path),
                detect_types=0,
                check_same_thread=False,
                timeout=30.0,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(SCHEMA)
            _seed_settings(connection)
            _CONNECTION = connection
        return _CONNECTION


def close() -> None:
    global _CONNECTION
    with _LOCK:
        if _CONNECTION is not None:
            try:
                _CONNECTION.close()
            except Exception:
                pass
            _CONNECTION = None


def reset_connection_for_tests(path: Optional[Path] = None) -> None:
    """Tests use this to point at a throwaway database file."""
    close()
    if path is not None:
        settings.DATABASE_PATH = Path(path)
    connect()


def _seed_settings(connection: sqlite3.Connection) -> None:
    now = int(time.time())
    for key, value in settings.DEFAULT_SETTINGS.items():
        connection.execute(
            "INSERT OR IGNORE INTO settings (key, value, updated_at_unix) "
            "VALUES (?, ?, ?)",
            (key, str(value), now),
        )
    connection.commit()


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
def get_settings() -> Dict[str, str]:
    connection = connect()
    rows = connection.execute("SELECT key, value FROM settings").fetchall()
    stored = {row["key"]: row["value"] for row in rows}
    merged = dict(settings.DEFAULT_SETTINGS)
    merged.update(stored)
    return merged


def get_setting(key: str, cast=None):
    value = get_settings().get(key)
    if value is None:
        return None
    if cast is None:
        cast = settings.SETTING_TYPES.get(key, str)
    try:
        return cast(value)
    except (TypeError, ValueError):
        return settings.DEFAULT_SETTINGS.get(key)


def set_settings(updates: Dict[str, Any]) -> Tuple[Dict[str, str], List[str]]:
    """Validate and persist settings.  Returns (current, rejected)."""
    connection = connect()
    now = int(time.time())
    rejected: List[str] = []
    for key, raw in updates.items():
        if key not in settings.DEFAULT_SETTINGS:
            rejected.append("%s is not a known setting" % key)
            continue
        caster = settings.SETTING_TYPES.get(key, str)
        try:
            value = caster(raw)
        except (TypeError, ValueError):
            rejected.append("%s expects a %s" % (key, caster.__name__))
            continue
        if key in settings.SETTING_BOUNDS:
            low, high = settings.SETTING_BOUNDS[key]
            if value < low or value > high:
                rejected.append("%s must be between %s and %s" % (key, low, high))
                continue
        connection.execute(
            "INSERT INTO settings (key, value, updated_at_unix) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at_unix = excluded.updated_at_unix",
            (key, str(value), now),
        )
    connection.commit()
    return get_settings(), rejected


# --------------------------------------------------------------------------- #
# Readings
# --------------------------------------------------------------------------- #
def _normalise_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def insert_reading(payload: Dict[str, Any]) -> Tuple[bool, Optional[int]]:
    """Insert one reading.  Returns (inserted, row_id_or_None_on_duplicate)."""
    connection = connect()
    columns = ", ".join(READING_COLUMNS)
    placeholders = ", ".join("?" for _ in READING_COLUMNS)
    values = [payload.get(column) for column in READING_COLUMNS]
    with _LOCK:
        try:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO readings (%s, received_at_unix) "
                "VALUES (%s, ?)" % (columns, placeholders),
                values + [int(time.time())],
            )
        except sqlite3.Error:
            connection.rollback()
            raise
        connection.commit()
        if cursor.rowcount == 0:
            return False, None
        return True, int(cursor.lastrowid)


def latest_reading(device_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    connection = connect()
    if device_id:
        row = connection.execute(
            "SELECT * FROM readings WHERE device_id = ? "
            "ORDER BY reading_timestamp DESC, id DESC LIMIT 1",
            (device_id,),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT * FROM readings ORDER BY reading_timestamp DESC, id DESC LIMIT 1"
        ).fetchone()
    return _normalise_row(row) if row else None


def history(hours: Optional[float] = None, limit: int = 500,
            since_unix: Optional[int] = None,
            until_unix: Optional[int] = None,
            device_id: Optional[str] = None) -> List[Dict[str, Any]]:
    connection = connect()
    clauses: List[str] = []
    params: List[Any] = []
    if hours is not None:
        clauses.append("received_at_unix >= ?")
        params.append(int(time.time() - hours * 3600))
    if since_unix is not None:
        clauses.append("received_at_unix >= ?")
        params.append(int(since_unix))
    if until_unix is not None:
        clauses.append("received_at_unix <= ?")
        params.append(int(until_unix))
    if device_id:
        clauses.append("device_id = ?")
        params.append(device_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    limit = max(1, min(int(limit), 20000))
    rows = connection.execute(
        "SELECT * FROM readings%s ORDER BY reading_timestamp DESC, id DESC LIMIT ?"
        % where,
        params + [limit],
    ).fetchall()
    return [_normalise_row(row) for row in rows]


def history_ascending(limit: int = 500) -> List[Dict[str, Any]]:
    connection = connect()
    limit = max(1, min(int(limit), 20000))
    rows = connection.execute(
        "SELECT * FROM readings ORDER BY reading_timestamp DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_normalise_row(row) for row in reversed(rows)]


def reading_count() -> int:
    connection = connect()
    return int(connection.execute("SELECT COUNT(*) AS n FROM readings").fetchone()["n"])


def stats() -> Dict[str, Any]:
    connection = connect()
    row = connection.execute(
        "SELECT COUNT(*) AS n, MIN(reading_timestamp) AS first_ts, "
        "MAX(reading_timestamp) AS last_ts, MAX(received_at_unix) AS last_rx "
        "FROM readings"
    ).fetchone()
    total = int(row["n"] or 0)

    def _agg(function: str, column: str) -> Optional[float]:
        result = connection.execute(
            "SELECT %s(%s) AS value FROM readings WHERE %s IS NOT NULL"
            % (function, column, column)
        ).fetchone()
        return float(result["value"]) if result and result["value"] is not None else None

    def _triple(column: str) -> Dict[str, Any]:
        return {"min": _agg("MIN", column),
                "max": _agg("MAX", column),
                "avg": _agg("AVG", column)}

    origins = connection.execute(
        "SELECT data_origin, COUNT(*) AS n FROM readings GROUP BY data_origin"
    ).fetchall()
    return {
        "total_readings": total,
        "first_timestamp": row["first_ts"],
        "last_timestamp": row["last_ts"],
        "last_received_unix": row["last_rx"],
        "last_received_seconds_ago": (
            int(time.time()) - int(row["last_rx"]) if row["last_rx"] else None
        ),
        "aggregates": {
            column: _triple(column)
            for column in (
                "solar_voltage", "wind_voltage", "turbine_rpm",
                "temperature_c", "humidity_percent", "solar_power", "wind_power",
            )
        },
        "data_origin_counts": {row_["data_origin"]: int(row_["n"]) for row_ in origins},
    }


# --------------------------------------------------------------------------- #
# Devices
# --------------------------------------------------------------------------- #
def touch_device(device_id: str, ip: Optional[str],
                 sensor_status: Optional[str]) -> None:
    connection = connect()
    now = int(time.time())
    with _LOCK:
        connection.execute(
            "INSERT INTO devices (device_id, first_seen_unix, last_seen_unix, "
            "last_ip, last_sensor_status, total_readings) VALUES (?, ?, ?, ?, ?, 1) "
            "ON CONFLICT(device_id) DO UPDATE SET "
            "last_seen_unix = excluded.last_seen_unix, "
            "last_ip = COALESCE(excluded.last_ip, devices.last_ip), "
            "last_sensor_status = COALESCE(excluded.last_sensor_status, "
            "devices.last_sensor_status), "
            "total_readings = devices.total_readings + 1",
            (device_id, now, now, ip, sensor_status),
        )
        connection.commit()


def list_devices(offline_after_s: int) -> List[Dict[str, Any]]:
    connection = connect()
    rows = connection.execute(
        "SELECT * FROM devices ORDER BY last_seen_unix DESC"
    ).fetchall()
    now = int(time.time())
    out: List[Dict[str, Any]] = []
    for row in rows:
        entry = _normalise_row(row)
        entry["seconds_since_last_seen"] = now - int(entry["last_seen_unix"])
        entry["online"] = int(entry["seconds_since_last_seen"] <= offline_after_s)
        out.append(entry)
    return out


def device_status(device_id: str, offline_after_s: int) -> Optional[Dict[str, Any]]:
    connection = connect()
    row = connection.execute(
        "SELECT * FROM devices WHERE device_id = ?", (device_id,)
    ).fetchone()
    if not row:
        return None
    entry = _normalise_row(row)
    now = int(time.time())
    entry["seconds_since_last_seen"] = now - int(entry["last_seen_unix"])
    entry["online"] = int(entry["seconds_since_last_seen"] <= offline_after_s)
    return entry


# --------------------------------------------------------------------------- #
# Predictions
# --------------------------------------------------------------------------- #
def insert_prediction(reading_id: Optional[int], device_id: Optional[str],
                      result: Dict[str, Any]) -> None:
    connection = connect()
    with _LOCK:
        connection.execute(
            "INSERT INTO predictions (reading_id, device_id, predicted_at_unix, "
            "predicted_power_w, predicted_condition, anomaly_probability, "
            "anomaly_flag, model_version, features_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                reading_id,
                device_id,
                int(time.time()),
                result.get("predicted_power_w"),
                result.get("predicted_condition"),
                result.get("anomaly_probability"),
                result.get("anomaly_flag"),
                result.get("model_version"),
                json.dumps(result.get("features", {})),
            ),
        )
        connection.commit()


def recent_predictions(limit: int = 100) -> List[Dict[str, Any]]:
    connection = connect()
    limit = max(1, min(int(limit), 5000))
    rows = connection.execute(
        "SELECT * FROM predictions ORDER BY predicted_at_unix DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_normalise_row(row) for row in rows]


def prediction_series(limit: int = 300) -> List[Dict[str, Any]]:
    """Stored predictions joined to the reading they were made from.

    This is what lets the analytics chart plot *actual vs predicted* on one
    shared time axis: ``actual_power_w`` comes from the stored reading (which is
    null for a node with no measurable load) and ``predicted_power_w`` from the
    model.  Returned newest-first; the route reverses it for charts.
    """
    connection = connect()
    limit = max(1, min(int(limit), 5000))
    rows = connection.execute(
        "SELECT p.id, p.reading_id, p.device_id, p.predicted_at_unix, "
        "p.predicted_power_w, p.predicted_condition, p.anomaly_probability, "
        "p.anomaly_flag, p.model_version, "
        "r.reading_timestamp, r.data_origin, "
        "r.solar_power, r.wind_power, "
        "(COALESCE(r.solar_power, 0.0) + COALESCE(r.wind_power, 0.0)) "
        "AS actual_power_w "
        "FROM predictions p LEFT JOIN readings r ON r.id = p.reading_id "
        "ORDER BY p.predicted_at_unix DESC, p.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_normalise_row(row) for row in rows]


# --------------------------------------------------------------------------- #
# Maintenance
# --------------------------------------------------------------------------- #
def export_csv(limit: int = 100000) -> Tuple[List[str], List[List[Any]]]:
    rows = history(limit=limit)
    columns = ["reading_timestamp", "received_at_unix", "device_id", "data_origin",
               "solar_voltage", "solar_current", "solar_power",
               "wind_voltage", "wind_current", "wind_power",
               "turbine_rpm", "temperature_c", "humidity_percent",
               "light_status", "light_level_lux", "sensor_status", "device_ip"]
    table = [[row.get(column) for column in columns] for row in rows]
    return columns, table


def purge_readings(older_than_unix: int) -> int:
    connection = connect()
    with _LOCK:
        # Delete dependent predictions first: the schema enforces the
        # predictions -> readings foreign key, so removing readings directly
        # would fail whenever a prediction references one of them.
        connection.execute(
            "DELETE FROM predictions WHERE reading_id IN "
            "(SELECT id FROM readings WHERE received_at_unix < ?)",
            (int(older_than_unix),),
        )
        cursor = connection.execute(
            "DELETE FROM readings WHERE received_at_unix < ?", (int(older_than_unix),)
        )
        connection.commit()
    return int(cursor.rowcount)


def purge_all_readings() -> int:
    connection = connect()
    with _LOCK:
        connection.execute("DELETE FROM predictions")
        cursor = connection.execute("DELETE FROM readings")
        connection.commit()
    return int(cursor.rowcount)
