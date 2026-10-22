"""Payload validation and normalisation."""

from __future__ import annotations

from backend.services import validation


def _base(**overrides):
    payload = {
        "device_id": "T-1",
        "timestamp": "2025-01-01T12:00:00Z",
        "solar_voltage": 5.0,
        "wind_voltage": 2.0,
        "turbine_rpm": 500.0,
        "sensor_status": "OK",
    }
    payload.update(overrides)
    return payload


def test_valid_payload_passes():
    row, errors = validation.validate_payload(_base())
    assert errors == []
    assert row is not None
    assert row["solar_voltage"] == 5.0
    assert row["data_origin"] == "hardware"


def test_firmware_aliases_are_applied():
    row, errors = validation.validate_payload(_base(
        temperature=31.5, humidity=44.0, light="bright"))
    assert errors == []
    assert row["temperature_c"] == 31.5
    assert row["humidity_percent"] == 44.0
    assert row["light_status"] == "bright"


def test_out_of_range_value_is_rejected_with_reason():
    row, errors = validation.validate_payload(_base(temperature=999.0))
    assert row is None
    assert any("temperature_c" in message for message in errors)


def test_missing_required_field_is_rejected():
    payload = _base()
    payload.pop("turbine_rpm")
    row, errors = validation.validate_payload(payload)
    assert row is None
    assert any("turbine_rpm" in message for message in errors)


def test_missing_sensor_status_is_rejected():
    payload = _base()
    payload.pop("sensor_status")
    row, errors = validation.validate_payload(payload)
    assert row is None
    assert any("sensor_status" in message for message in errors)


def test_power_without_current_is_not_believed():
    row, errors = validation.validate_payload(_base(solar_power=12.0))
    assert row is None
    assert any("solar_power" in message for message in errors)


def test_power_is_derived_when_current_is_present():
    row, errors = validation.validate_payload(_base(solar_current=0.5))
    assert errors == []
    assert abs(row["solar_power"] - 2.5) < 1e-9


def test_unknown_field_is_reported():
    row, errors = validation.validate_payload(_base(mystery_field=1))
    assert row is None
    assert any("unrecognised" in message for message in errors)


def test_bad_light_status_is_rejected():
    row, errors = validation.validate_payload(_base(light_status="greenish"))
    assert row is None
    assert any("light_status" in message for message in errors)


def test_missing_timestamp_defaults_to_now():
    payload = _base()
    payload.pop("timestamp")
    row, errors = validation.validate_payload(payload)
    assert errors == []
    assert row["reading_timestamp"] is not None


def test_odd_precision_timestamp_is_accepted():
    row, errors = validation.validate_payload(
        _base(timestamp="2025-01-01T12:00:00.123456789Z"))
    assert errors == []
    assert row is not None


def test_summarise_reports_current_unmeasurable():
    row, _ = validation.validate_payload(_base())
    view = validation.summarise_reading(row)
    assert view["current_measurable"] is False
    assert view["solar_current"] is None
    assert view["total_est_power_w"] == 0.0


def test_summarise_keeps_nulls_as_nulls():
    row, _ = validation.validate_payload(_base(light_level_lux=None))
    view = validation.summarise_reading(row)
    assert view["light_level_lux"] is None
