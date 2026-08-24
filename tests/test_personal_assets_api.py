from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.core.database import get_db


NOW = datetime(2026, 8, 24, 1, 0, tzinfo=UTC).isoformat()


def client(db) -> TestClient:
    api = FastAPI()
    api.include_router(routes.router)
    api.dependency_overrides[get_db] = lambda: db
    return TestClient(api)


def test_personal_asset_opening_dashboard_and_reversal_api(db):
    api = client(db)
    account = api.post(
        "/api/v1/personal-assets/accounts",
        json={"name": "銀行", "institution": "臺灣銀行", "asset_type": "TWD", "currency": "TWD"},
    )
    assert account.status_code == 201

    opening = api.post(
        "/api/v1/personal-assets/opening",
        json={
            "account_id": account.json()["id"],
            "asset_type": "TWD",
            "symbol": "TWD",
            "name": "活期存款",
            "quantity": "50000",
            "total_cost": "50000",
            "current_value": "50000",
            "occurred_at": NOW,
        },
    )
    assert opening.status_code == 201
    assert opening.json()["current_value"] == "50000.00"

    dashboard = api.get("/api/v1/personal-assets/dashboard?days=30")
    assert dashboard.status_code == 200
    assert dashboard.json()["total_value"] == "50000.00"

    opening_tx = api.get("/api/v1/personal-assets/transactions").json()[0]
    reversed_tx = api.post(
        f'/api/v1/personal-assets/transactions/{opening_tx["id"]}/reverse',
        json={"occurred_at": NOW, "reason": "期初輸入錯誤"},
    )
    assert reversed_tx.status_code == 201
    assert api.get("/api/v1/personal-assets/dashboard").json()["total_value"] == "0.00"


def test_personal_asset_api_rejects_zero_amount_buy(db):
    response = client(db).post(
        "/api/v1/personal-assets/transactions",
        json={
            "kind": "BUY",
            "source_position_id": 1,
            "target_position_id": 2,
            "quantity": "1",
            "gross_amount": "0",
            "fees": "0",
            "occurred_at": NOW,
        },
    )
    assert response.status_code == 422
