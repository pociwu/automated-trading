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


def test_personal_asset_opening_reset_clears_data_but_keeps_accounts(db):
    api = client(db)
    bank = api.post(
        "/api/v1/personal-assets/accounts",
        json={"name": "銀行", "institution": "臺灣銀行", "asset_type": "TWD", "currency": "TWD"},
    ).json()
    broker = api.post(
        "/api/v1/personal-assets/accounts",
        json={"name": "股票", "institution": "富邦證券", "asset_type": "STOCK", "currency": "TWD"},
    ).json()
    for account, asset_type, symbol, quantity, total_cost in [
        (bank, "TWD", "TWD", "50000", "50000"),
        (broker, "STOCK", "4916", "100", "4550"),
    ]:
        response = api.post(
            "/api/v1/personal-assets/opening",
            json={
                "account_id": account["id"],
                "asset_type": asset_type,
                "symbol": symbol,
                "name": symbol,
                "quantity": quantity,
                "total_cost": total_cost,
                "current_value": total_cost,
                "occurred_at": NOW,
            },
        )
        assert response.status_code == 201
    assert api.post("/api/v1/personal-assets/snapshots").status_code == 201

    wrong_confirmation = api.post(
        "/api/v1/personal-assets/opening/reset",
        json={"confirmation": "RESET"},
    )
    reset = api.post(
        "/api/v1/personal-assets/opening/reset",
        json={"confirmation": "清空期初資產"},
    )

    assert wrong_confirmation.status_code == 422
    assert reset.status_code == 200
    assert reset.json() == {
        "deleted_positions": 2,
        "deleted_transactions": 2,
        "deleted_snapshots": 1,
    }
    assert len(api.get("/api/v1/personal-assets/accounts").json()) == 2
    assert api.get("/api/v1/personal-assets/transactions").json() == []
    dashboard = api.get("/api/v1/personal-assets/dashboard").json()
    assert dashboard["total_value"] == "0.00"
    assert dashboard["positions"] == []
    assert dashboard["snapshots"] == []


def test_personal_asset_opening_reset_rejects_formal_transactions(db):
    api = client(db)
    bank = api.post(
        "/api/v1/personal-assets/accounts",
        json={"name": "銀行", "institution": "臺灣銀行", "asset_type": "TWD", "currency": "TWD"},
    ).json()
    broker = api.post(
        "/api/v1/personal-assets/accounts",
        json={"name": "股票", "institution": "富邦證券", "asset_type": "STOCK", "currency": "TWD"},
    ).json()
    cash = api.post(
        "/api/v1/personal-assets/opening",
        json={
            "account_id": bank["id"], "asset_type": "TWD", "symbol": "TWD", "name": "活存",
            "quantity": "50000", "total_cost": "50000", "current_value": "50000", "occurred_at": NOW,
        },
    ).json()
    stock = api.post(
        "/api/v1/personal-assets/opening",
        json={
            "account_id": broker["id"], "asset_type": "STOCK", "symbol": "4916", "name": "事欣科",
            "quantity": "100", "total_cost": "4550", "current_value": "4550", "occurred_at": NOW,
        },
    ).json()
    bought = api.post(
        "/api/v1/personal-assets/transactions",
        json={
            "kind": "BUY", "source_position_id": cash["id"], "target_position_id": stock["id"],
            "quantity": "10", "gross_amount": "500", "fees": "0", "occurred_at": NOW,
        },
    )
    assert bought.status_code == 201

    reset = api.post(
        "/api/v1/personal-assets/opening/reset",
        json={"confirmation": "清空期初資產"},
    )

    assert reset.status_code == 400
    assert "已有買進、賣出或其他正式資產異動" in reset.json()["detail"]
