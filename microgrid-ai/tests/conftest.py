"""Shared pytest fixtures.

Every test that touches the database runs against a throwaway SQLite file in a
temp directory, so the real ``data/db/microgrid.db`` is never modified by the
test suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import db  # noqa: E402
from config import settings  # noqa: E402


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the whole app at a fresh database for the duration of one test."""
    db.close()
    monkeypatch.setattr(settings, "DATABASE_PATH", tmp_path / "test_microgrid.db")
    db.connect()
    yield tmp_path / "test_microgrid.db"
    db.close()


@pytest.fixture()
def client(temp_db):
    """A Flask test client wired to the temp database, demo feed switched off."""
    from backend.app import create_app

    app = create_app(start_demo_feed=False)
    app.config.update(TESTING=True, JSON_SORT_KEYS=False)
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def device_token():
    """The token the seeded database expects for ingestion."""
    return db.get_setting("device_token", str) or ""


@pytest.fixture()
def hardware_payload():
    """A well-formed firmware payload, current deliberately unmeasurable."""
    return {
        "device_id": "TEST-NODE-01",
        "timestamp": "2026-01-15T10:30:00+00:00",
        "solar_voltage": 5.12,
        "solar_current": None,
        "solar_power": None,
        "wind_voltage": 2.44,
        "wind_current": None,
        "wind_power": None,
        "turbine_rpm": 540.0,
        "temperature": 29.4,
        "humidity": 58.1,
        "light_status": "bright",
        "sensor_status": "OK",
        "device_ip": "192.168.43.37",
    }
