"""Validation and normalisation of incoming device payloads.

The ESP8266 firmware posts the documented JSON shape::

    {
      "timestamp":      "2025-01-01T12:00:00",
      "solar_voltage":  5.42,
      "solar_current":  null,          <- NULL when no load is connected
      "solar_power":    null,
      "wind_voltage":   2.81,
      "wind_current":   null,
      "wind_power":     null,
      "turbine_rpm":    640.0,
      "temperature":    28.5,
      "humidity":       61.0,
      "light_status":   "bright",
      "sensor_status":  "OK",
      "device_ip":      "192.168.43.37"
    }

Everything is converted into the flat column set used by SQLite.  Invalid
payloads are rejected with a precise, human-readable reason rather than being
silently coerced, so a wiring or firmware bug is visible immediately.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Plausible physical bounds for a small lab-scale microgrid node.  Anything
# outside these ranges is treated as a sensor fault or a wiring mistake.
BOUNDS = {
    "solar_voltage": (0.0, 30.0, "V"),
    "solar_current": (0.0, 20.0, "A"),
    "solar_power": (0.0, 300.0, "W"),
    "wind_voltage": (0.0, 30.0, "V"),
    "wind_current": (0.0, 20.0, "A"),
    "wind_power": (0.0, 300.0, "W"),
    "turbine_rpm": (0.0, 20000.0, "RPM"),
    "temperature_c": (-40.0, 85.0, "degC"),
    "humidity_percent": (0.0, 100.0, "%"),
    "light_level_lux": (0.0, 200000.0, "lux"),
}

# Firmware field name -> internal column name.
ALIASES = {
    "temperature": "temperature_c",
    "temp": "temperature_c",
    "temperature_c": "temperature_c",
    "humidity": "humidity_percent",
    "humidity_percent": "humidity_percent",
    "rh": "humidity_percent",
    "light": "light_status",
    "light_status": "light_status",
    "light_level_lux": "light_level_lux",
    "lux": "light_level_lux",
}

REQUIRED_NUMERIC = ["solar_voltage", "wind_voltage", "turbine_rpm"]
OPTIONAL_NUMERIC = [
    "solar_current", "solar_power", "wind_current", "wind_power",
    "temperature_c", "humidity_percent", "light_level_lux",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_timestamp(raw: Any) -> Tuple[Optional[str], Optional[str]]:
    """Return (iso_string, error).

    Python 3.8's ``datetime.fromisoformat`` only accepts 3 or 6 fractional
    digits, but RTC modules and JavaScript emit other widths, so
    ``dateutil.isoparse`` is used as a fallback before declaring the value
    invalid.
    """
    if raw is None or raw == "":
        return _now_iso(), None
    if not isinstance(raw, str):
        return None, "timestamp must be an ISO-8601 string"
    text = raw.strip()
    if not text:
        return _now_iso(), None

    parsed: Optional[datetime] = None
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            from dateutil import parser as date_parser

            parsed = date_parser.isoparse(text)
        except Exception:
            parsed = None
    if parsed is None:
        return None, "timestamp is not a valid ISO-8601 value: %r" % raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat(), None


def _coerce_float(raw: Any, field: str, errors: List[str],
                  required: bool) -> Optional[float]:
    """Accept numbers, numeric strings and explicit nulls."""
    if raw is None or raw == "" or (isinstance(raw, str) and raw.lower() in
                                    ("null", "nan", "none")):
        if required:
            errors.append("%s is required and cannot be null" % field)
        return None
    if isinstance(raw, bool):
        errors.append("%s must be a number, got a boolean" % field)
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        errors.append("%s must be numeric, got %r" % (field, raw))
        return None
    if math.isnan(value) or math.isinf(value):
        errors.append("%s must be a finite number" % field)
        return None
    low, high, unit = BOUNDS.get(field, (-1e9, 1e9, ""))
    if value < low or value > high:
        errors.append("%s = %.4f is outside the plausible range %.2f-%.2f %s"
                      % (field, value, low, high, unit))
        return None
    return round(value, 6)


def validate_payload(payload: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Validate one device payload.

    Returns ``(normalised_row, errors)``.  ``normalised_row`` is ``None`` when
    the payload is unusable; ``errors`` is a list of precise reasons.
    """
    errors: List[str] = []

    if payload is None:
        return None, ["request body was empty"]
    if not isinstance(payload, dict):
        return None, ["request body must be a JSON object, got %s"
                      % type(payload).__name__]

    unknown = [key for key in payload
               if key not in _known_keys() and key not in ("device_token", "id")]
    if unknown:
        errors.append("unrecognised fields: %s" % ", ".join(sorted(unknown)))

    # Firmware field names are aliased onto internal column names so that
    # `temperature` / `humidity` / `light` all land in the right columns.
    normalised: Dict[str, Any] = {}
    for key, value in payload.items():
        normalised[ALIASES.get(key, key)] = value
    payload = normalised

    # ---- timestamp -------------------------------------------------------
    timestamp, timestamp_error = _parse_timestamp(payload.get("timestamp"))
    if timestamp_error:
        errors.append(timestamp_error)

    # ---- device identity -------------------------------------------------
    device_id = payload.get("device_id") or payload.get("id")
    if device_id is not None:
        device_id = str(device_id).strip()
        if not device_id:
            device_id = None
        elif len(device_id) > 64:
            errors.append("device_id must be 64 characters or fewer")

    device_ip = payload.get("device_ip")
    if device_ip is not None:
        device_ip = str(device_ip).strip()[:64] or None

    # ---- required numerics ----------------------------------------------
    values: Dict[str, Optional[float]] = {}
    for field in REQUIRED_NUMERIC:
        values[field] = _coerce_float(payload.get(field), field, errors, required=True)
    for field in OPTIONAL_NUMERIC:
        values[field] = _coerce_float(payload.get(field), field, errors, required=False)

    # ---- sensor status ---------------------------------------------------
    sensor_status = payload.get("sensor_status")
    if sensor_status is not None:
        sensor_status = str(sensor_status).strip()[:120] or None
    if sensor_status is None:
        errors.append("sensor_status is required (use 'OK' when every sensor is healthy)")

    light_status = payload.get("light_status")
    if light_status is not None:
        light_status = str(light_status).strip().lower()[:32] or None
        if light_status not in (None, "bright", "dim", "dark", "unknown"):
            errors.append("light_status must be bright|dim|dark|unknown, got %r"
                          % light_status)

    # ---- derived power when the node could not compute it ----------------
    for prefix in ("solar", "wind"):
        voltage = values.get("%s_voltage" % prefix)
        current = values.get("%s_current" % prefix)
        power = values.get("%s_power" % prefix)
        if power is None and voltage is not None and current is not None:
            values["%s_power" % prefix] = round(voltage * current, 6)
        if power is not None and voltage is not None and current is None:
            # Power claimed without a current measurement: not credible for
            # this hardware, so drop it rather than present a made-up number.
            errors.append(
                "%s_power was supplied without %s_current; generated current "
                "cannot be measured without a connected load, so power is "
                "reported as null" % (prefix, prefix)
            )
            values["%s_power" % prefix] = None

    if errors:
        return None, errors

    row = {
        "device_id": device_id,
        "reading_timestamp": timestamp,
        "data_origin": "hardware",
        "solar_voltage": values["solar_voltage"],
        "solar_current": values["solar_current"],
        "solar_power": values["solar_power"],
        "wind_voltage": values["wind_voltage"],
        "wind_current": values["wind_current"],
        "wind_power": values["wind_power"],
        "turbine_rpm": values["turbine_rpm"],
        "temperature_c": values["temperature_c"],
        "humidity_percent": values["humidity_percent"],
        "light_status": light_status,
        "light_level_lux": values["light_level_lux"],
        "sensor_status": sensor_status,
        "device_ip": device_ip,
        "raw_json": None,
    }
    return row, []


def _known_keys() -> set:
    keys = {
        "timestamp", "device_id", "device_ip", "sensor_status",
        "solar_voltage", "solar_current", "solar_power",
        "wind_voltage", "wind_current", "wind_power",
        "turbine_rpm", "temperature", "temperature_c", "humidity",
        "humidity_percent", "light_status", "light_level_lux",
    }
    keys.update(ALIASES.keys())
    return keys


def summarise_reading(row: Dict[str, Any]) -> Dict[str, Any]:
    """Compact, dashboard-ready view of one reading (nulls stay null)."""
    def _round(value, digits=3):
        return None if value is None else round(float(value), digits)

    return {
        "timestamp": row.get("reading_timestamp"),
        "device_id": row.get("device_id"),
        "data_origin": row.get("data_origin"),
        "solar_voltage": _round(row.get("solar_voltage")),
        "solar_current": _round(row.get("solar_current"), 4),
        "solar_power": _round(row.get("solar_power"), 4),
        "wind_voltage": _round(row.get("wind_voltage")),
        "wind_current": _round(row.get("wind_current"), 4),
        "wind_power": _round(row.get("wind_power"), 4),
        "turbine_rpm": _round(row.get("turbine_rpm"), 1),
        "temperature_c": _round(row.get("temperature_c"), 2),
        "humidity_percent": _round(row.get("humidity_percent"), 2),
        "light_status": row.get("light_status"),
        "light_level_lux": _round(row.get("light_level_lux"), 0),
        "sensor_status": row.get("sensor_status"),
        "device_ip": row.get("device_ip"),
        "total_est_power_w": _round(
            (row.get("solar_power") or 0.0) + (row.get("wind_power") or 0.0), 4),
        "current_measurable": not (
            row.get("solar_current") is None and row.get("wind_current") is None
        ),
    }
