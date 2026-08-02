from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.core.database import get_db
from app.models.entities import MarketDataStatus
from app.services.market_data_health import MarketDataHealthService


def test_market_data_health_reports_connected_fresh_provider(db):
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add(
        MarketDataStatus(
            provider="fugle",
            connected=True,
            subscribed_symbols=2,
            last_message_at=now,
            last_tick_at=now,
            updated_at=now,
        )
    )
    db.commit()

    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[get_db] = lambda: db

    response = TestClient(api).get("/api/v1/health/market-data")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "fugle",
        "status": "healthy",
        "connected": True,
        "subscribed_symbols": 2,
        "last_message_at": now.isoformat(),
        "last_tick_at": now.isoformat(),
        "stale": False,
        "detail": None,
    }


def test_health_service_rejects_stale_source_tick(db):
    now = datetime(2026, 8, 2, 1, 0, 0)
    db.add(MarketDataStatus(provider="fugle", connected=True, subscribed_symbols=1, updated_at=now))
    db.commit()
    stale_source = now - timedelta(seconds=11)
    source_time = int(stale_source.replace(tzinfo=UTC).timestamp() * 1_000_000)

    accepted = MarketDataHealthService(db, now=now).record_tick(source_time)
    health = MarketDataHealthService(db, now=now).read()

    assert accepted is False
    assert health.status == "degraded"
    assert health.last_tick_at is None
    assert health.detail == "Rejected stale market tick"


def test_health_service_records_connection_lifecycle(db):
    now = datetime(2026, 8, 2, 1, 0, 0)
    service = MarketDataHealthService(db, now=now)

    service.record_connected(subscribed_symbols=3)
    connected = service.read()
    service.record_disconnected("socket closed")
    disconnected = service.read()

    assert connected.connected is True
    assert connected.subscribed_symbols == 3
    assert connected.status == "degraded"
    assert disconnected.connected is False
    assert disconnected.status == "unavailable"
    assert disconnected.detail == "socket closed"


def test_health_service_reports_idle_without_subscriptions(db):
    service = MarketDataHealthService(db, now=datetime(2026, 8, 2, 1, 0, 0))

    service.record_idle()

    health = service.read()
    assert health.status == "idle"
    assert health.connected is False
    assert health.subscribed_symbols == 0
    assert health.stale is False
