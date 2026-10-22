"""Simulated telemetry feed.

When ``demo_mode`` is enabled the platform replays rows from the training
dataset into the live database so the dashboard, charts and API can be
demonstrated end-to-end without a physical node.

Every row this service writes is tagged ``data_origin = 'simulated'`` and the
dashboard renders those values separately from ``hardware`` readings.  A real
ESP8266 that starts posting takes priority: the feeder pauses as soon as fresh
hardware telemetry arrives and resumes only when the node goes quiet again.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from backend import db
from ml import preprocess

SIMULATED_DEVICE_ID = "SIM-GRID-01"


class DemoFeed:
    """Background writer that replays the dataset into the live database."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._frame: Optional[pd.DataFrame] = None
        self._cursor = 0
        self._last_write_unix: Optional[float] = None
        self._started_at: Optional[float] = None
        self._writes = 0
        self._paused_reason: Optional[str] = None
        self._last_stamp: Optional[int] = None

    def _unique_stamp(self) -> str:
        """Whole-second stamp that always advances, so rapid ticks never clash.

        Readings are deduplicated on ``(device_id, reading_timestamp)``; two
        ticks inside the same wall-clock second would otherwise collide and be
        rejected as duplicates.
        """
        with self._lock:
            now = int(time.time())
            if self._last_stamp is None or now > self._last_stamp:
                self._last_stamp = now
            else:
                self._last_stamp += 1
            stamp = self._last_stamp
        return pd.Timestamp(stamp, unit="s", tz="UTC").isoformat()

    # ------------------------------------------------------------------ #
    # Data
    # ------------------------------------------------------------------ #
    def _load_frame(self) -> pd.DataFrame:
        if self._frame is None:
            frame = preprocess.load_dataset()
            # Replay at a fixed stride so a "tick" covers a representative
            # slice of the day rather than 5-minute neighbours.
            self._frame = frame.reset_index(drop=True)
        return self._frame

    def _row_to_payload(self, row: pd.Series) -> Dict[str, Any]:
        stamp = pd.to_datetime(row["timestamp"])
        # Re-stamp to "now" so the replay looks live on every dashboard.
        now = pd.Timestamp.now(tz="UTC").replace(microsecond=0)
        payload = {
            "device_id": SIMULATED_DEVICE_ID,
            "reading_timestamp": now.isoformat(),
            "data_origin": "simulated",
            "solar_voltage": float(row["solar_voltage"]),
            "solar_current": float(row["solar_current_est_a"]),
            "solar_power": float(row["solar_power_est_w"]),
            "wind_voltage": float(row["wind_voltage"]),
            "wind_current": float(row["wind_current_est_a"]),
            "wind_power": float(row["wind_power_est_w"]),
            "turbine_rpm": float(row["turbine_rpm"]),
            "temperature_c": float(row["temperature_c"]),
            "humidity_percent": float(row["humidity_percent"]),
            "light_status": _light_status(float(row["light_level_lux"])),
            "light_level_lux": float(row["light_level_lux"]),
            "sensor_status": "SIMULATED",
            "device_ip": "127.0.0.1",
            "raw_json": json.dumps({
                "simulated": True,
                "source_timestamp": str(stamp),
                "source_condition": str(row.get("operating_condition", "")),
                "source_anomaly": int(row.get("anomaly_label", 0)),
                "anomaly_type": str(row.get("anomaly_type", "")),
            }),
        }
        return payload

    def _stride(self) -> int:
        """Advance so successive ticks span a whole day of simulated time."""
        frame = self._load_frame()
        return max(1, len(frame) // 288)

    # ------------------------------------------------------------------ #
    # Control
    # ------------------------------------------------------------------ #
    def seed(self, count: int = 240, spacing_seconds: int = 300) -> Dict[str, int]:
        """Back-fill ``count`` evenly spaced historical points (for charts).

        Returns ``{"inserted": n, "skipped": m}``.  Rows are skipped when the
        dataset itself contains an implausible value (for example the injected
        out-of-range temperature fault), because the same validation that
        guards the live ingest endpoint rejects them here too.
        """
        frame = self._load_frame()
        if frame.empty:
            return {"inserted": 0, "skipped": 0}
        count = max(1, min(int(count), 5000))
        start_index = (self._cursor - count * self._stride()) % len(frame)
        inserted = 0
        skipped = 0
        now = time.time()
        from backend.services import validation

        for offset in range(count):
            index = (start_index + offset * self._stride()) % len(frame)
            row = frame.iloc[index]
            payload = self._row_to_payload(row)
            payload["reading_timestamp"] = pd.Timestamp(
                int(now) - (count - offset) * spacing_seconds, unit="s", tz="UTC"
            ).isoformat()
            row_view, errors = validation.validate_payload({
                "timestamp": payload["reading_timestamp"],
                "device_id": payload["device_id"],
                "solar_voltage": payload["solar_voltage"],
                "solar_current": payload["solar_current"],
                "wind_voltage": payload["wind_voltage"],
                "wind_current": payload["wind_current"],
                "turbine_rpm": payload["turbine_rpm"],
                "temperature": payload["temperature_c"],
                "humidity": payload["humidity_percent"],
                "light_level_lux": payload["light_level_lux"],
                "light_status": payload["light_status"],
                "sensor_status": payload["sensor_status"],
                "device_ip": payload["device_ip"],
            })
            if errors or row_view is None:
                skipped += 1
                continue
            row_view["data_origin"] = "simulated"
            row_view["raw_json"] = payload["raw_json"]
            ok, _ = db.insert_reading(row_view)
            if ok:
                inserted += 1
                db.touch_device(SIMULATED_DEVICE_ID, payload["device_ip"],
                                "SIMULATED")
            else:
                skipped += 1
        with self._lock:
            self._cursor = (start_index + count * self._stride()) % len(frame)
        return {"inserted": inserted, "skipped": skipped}

    def tick(self) -> Optional[Dict[str, Any]]:
        """Insert exactly one reading and return it.

        Some dataset rows carry the deliberately injected out-of-range fault
        and are rejected by the same validation that guards live ingest.  When
        that happens the cursor simply advances to the next replayable row so a
        tick never fails outright.
        """
        frame = self._load_frame()
        if frame.empty:
            return None

        from backend.services import validation

        attempts = 0
        max_attempts = min(len(frame), 1024)
        while attempts < max_attempts:
            attempts += 1
            with self._lock:
                row = frame.iloc[self._cursor % len(frame)]
                self._cursor = (self._cursor + self._stride()) % len(frame)
                payload = self._row_to_payload(row)
                payload["reading_timestamp"] = self._unique_stamp()

            row_view, errors = validation.validate_payload({
                "timestamp": payload["reading_timestamp"],
                "device_id": payload["device_id"],
                "solar_voltage": payload["solar_voltage"],
                "solar_current": payload["solar_current"],
                "wind_voltage": payload["wind_voltage"],
                "wind_current": payload["wind_current"],
                "turbine_rpm": payload["turbine_rpm"],
                "temperature": payload["temperature_c"],
                "humidity": payload["humidity_percent"],
                "light_level_lux": payload["light_level_lux"],
                "light_status": payload["light_status"],
                "sensor_status": payload["sensor_status"],
                "device_ip": payload["device_ip"],
            })
            if errors or row_view is None:
                continue
            row_view["data_origin"] = "simulated"
            row_view["raw_json"] = payload["raw_json"]
            ok, _row_id = db.insert_reading(row_view)
            if not ok:
                continue
            db.touch_device(SIMULATED_DEVICE_ID, payload["device_ip"], "SIMULATED")
            with self._lock:
                self._writes += 1
                self._last_write_unix = time.time()
            return db.latest_reading(SIMULATED_DEVICE_ID)
        return None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._started_at = time.time()
            self._thread = threading.Thread(
                target=self._run, name="demo-feed", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)
        with self._lock:
            self._thread = None

    def _run(self) -> None:
        from backend.services import inference

        while not self._stop.is_set():
            try:
                settings_map = db.get_settings()
                if str(settings_map.get("demo_mode", "0")) != "1":
                    self._paused_reason = "demo_mode disabled"
                    self._stop.wait(3.0)
                    continue

                interval = max(1, int(settings_map.get("sampling_interval_s", 5)))
                offline_after = int(settings_map.get("device_offline_after_s", 90))

                devices = db.list_devices(offline_after)
                hardware_online = any(
                    device["online"] and device["device_id"] != SIMULATED_DEVICE_ID
                    for device in devices
                )
                if hardware_online:
                    self._paused_reason = "live hardware telemetry detected"
                    self._stop.wait(interval)
                    continue

                self._paused_reason = None
                reading = self.tick()
                if reading:
                    try:
                        result = inference.SERVICE.predict(
                            reading,
                            threshold=float(settings_map.get("anomaly_threshold", 0.5)),
                        )
                        db.insert_prediction(reading.get("id"),
                                             reading.get("device_id"), result)
                    except Exception:
                        pass
                self._stop.wait(interval)
            except Exception as exc:  # keep the service alive
                self._paused_reason = "error: %s" % exc
                self._stop.wait(5.0)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": bool(self._thread and self._thread.is_alive()),
                "device_id": SIMULATED_DEVICE_ID,
                "writes": self._writes,
                "cursor": self._cursor,
                "started_at_unix": self._started_at,
                "last_write_unix": self._last_write_unix,
                "paused_reason": self._paused_reason,
            }


def _light_status(lux: float) -> str:
    if lux >= 40000:
        return "bright"
    if lux >= 500:
        return "dim"
    if lux >= 5:
        return "dim"
    return "dark"


FEED = DemoFeed()
