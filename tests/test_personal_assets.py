from datetime import UTC, datetime
from decimal import Decimal

from app.schemas.personal_assets import (
    PersonalAssetAccountCreate,
    PersonalAssetOpeningCreate,
    PersonalAssetType,
    PersonalAssetTransactionCreate,
    PersonalTransactionKind,
)
from app.services.personal_assets import PersonalAssetService
from app.services.personal_asset_valuation import PersonalAssetValuationService


NOW = datetime(2026, 8, 24, 1, 0, tzinfo=UTC)


def account(service, name: str, asset_type: PersonalAssetType):
    return service.create_account(
        PersonalAssetAccountCreate(name=name, institution="測試機構", asset_type=asset_type, currency="TWD")
    )


def opening(service, account_id, asset_type, symbol, quantity, cost, value):
    return service.opening(
        PersonalAssetOpeningCreate(
            account_id=account_id,
            asset_type=asset_type,
            symbol=symbol,
            name=symbol,
            quantity=Decimal(quantity),
            total_cost=Decimal(cost),
            current_value=Decimal(value),
            occurred_at=NOW,
        )
    )


def test_buy_and_sell_move_cash_and_use_weighted_average_cost(db):
    service = PersonalAssetService(db)
    bank = account(service, "銀行", PersonalAssetType.TWD)
    broker = account(service, "券商", PersonalAssetType.STOCK)
    cash = opening(service, bank.id, PersonalAssetType.TWD, "TWD", "100000", "100000", "100000")
    stock = opening(service, broker.id, PersonalAssetType.STOCK, "2330", "10", "1000", "1200")

    sold = service.transact(
        PersonalAssetTransactionCreate(
            kind=PersonalTransactionKind.SELL,
            source_position_id=stock.id,
            target_position_id=cash.id,
            quantity=Decimal("4"),
            gross_amount=Decimal("600"),
            fees=Decimal("0"),
            occurred_at=NOW,
        )
    )

    assert sold.cost_basis == Decimal("400.00")
    assert sold.realized_pnl == Decimal("200.00")
    assert stock.quantity == Decimal("6.00000000")
    assert stock.total_cost == Decimal("600.00")
    assert cash.quantity == Decimal("100600.00000000")

    bought = service.transact(
        PersonalAssetTransactionCreate(
            kind=PersonalTransactionKind.BUY,
            source_position_id=cash.id,
            target_position_id=stock.id,
            quantity=Decimal("2"),
            gross_amount=Decimal("260"),
            fees=Decimal("10"),
            occurred_at=NOW,
        )
    )

    assert bought.cost_basis == Decimal("270.00")
    assert stock.quantity == Decimal("8.00000000")
    assert stock.total_cost == Decimal("870.00")
    assert cash.quantity == Decimal("100330.00000000")


def test_reversal_restores_both_positions(db):
    service = PersonalAssetService(db)
    bank = account(service, "銀行", PersonalAssetType.TWD)
    broker = account(service, "券商", PersonalAssetType.STOCK)
    cash = opening(service, bank.id, PersonalAssetType.TWD, "TWD", "1000", "1000", "1000")
    stock = opening(service, broker.id, PersonalAssetType.STOCK, "2330", "2", "200", "240")
    tx = service.transact(
        PersonalAssetTransactionCreate(
            kind=PersonalTransactionKind.BUY,
            source_position_id=cash.id,
            target_position_id=stock.id,
            quantity=Decimal("1"),
            gross_amount=Decimal("120"),
            fees=Decimal("5"),
            occurred_at=NOW,
        )
    )

    reversal = service.reverse(tx.id, NOW, "輸入錯誤")

    assert reversal.reversal_of_id == tx.id
    assert cash.quantity == Decimal("1000.00000000")
    assert stock.quantity == Decimal("2.00000000")
    assert stock.total_cost == Decimal("200.00")


def test_dashboard_and_snapshot_keep_personal_assets_separate(db):
    service = PersonalAssetService(db)
    bank = account(service, "銀行", PersonalAssetType.TWD)
    gold_account = account(service, "黃金", PersonalAssetType.GOLD)
    cash = opening(service, bank.id, PersonalAssetType.TWD, "TWD", "1000", "1000", "1000")
    opening(service, gold_account.id, PersonalAssetType.GOLD, "BOT_GOLD_TWD", "2", "8000", "9000")

    valuation = PersonalAssetValuationService(db)
    dashboard = valuation.dashboard()
    snapshot = valuation.create_snapshot(NOW)
    gold = next(row for row in dashboard["positions"] if row.asset_type == PersonalAssetType.GOLD.value)

    assert dashboard["total_value"] == Decimal("10000.00")
    assert dashboard["total_basis"] == Decimal("9000.00")
    assert dashboard["estimated_difference"] == Decimal("1000.00")
    assert snapshot.twd_value == Decimal("1000.00")
    assert snapshot.gold_value == Decimal("9000.00")
    assert gold.quantity == Decimal("2.00000000")
    assert gold.total_cost == Decimal("8000.00")
    assert gold.average_cost == Decimal("4000.00")
    assert gold.acquired_at == NOW.replace(tzinfo=None)
    assert cash.quantity == Decimal("1000.00000000")
    assert [row.kind for row in service.transactions()] == ["OPENING", "OPENING"]


def test_opening_can_be_reversed_and_reentered(db):
    service = PersonalAssetService(db)
    bank = account(service, "銀行", PersonalAssetType.TWD)
    cash = opening(service, bank.id, PersonalAssetType.TWD, "TWD", "1000", "1000", "1000")
    opening_tx = next(row for row in service.transactions() if row.kind == PersonalTransactionKind.OPENING.value)

    service.reverse(opening_tx.id, NOW, "期初餘額輸入錯誤")

    assert cash.active is False
    assert cash.quantity == Decimal("0")
    corrected = opening(service, bank.id, PersonalAssetType.TWD, "TWD", "1200", "1200", "1200")
    assert corrected.id == cash.id
    assert corrected.quantity == Decimal("1200.00000000")


def test_partial_insurance_surrender_and_reversal(db):
    service = PersonalAssetService(db)
    bank = account(service, "銀行", PersonalAssetType.TWD)
    insurer = account(service, "保險", PersonalAssetType.INSURANCE)
    cash = opening(service, bank.id, PersonalAssetType.TWD, "TWD", "1000", "1000", "1000")
    policy = opening(service, insurer.id, PersonalAssetType.INSURANCE, "POLICY-A", "1", "100000", "90000")

    tx = service.transact(
        PersonalAssetTransactionCreate(
            kind=PersonalTransactionKind.SURRENDER,
            source_position_id=policy.id,
            target_position_id=cash.id,
            quantity=Decimal("0.25"),
            gross_amount=Decimal("24000"),
            fees=Decimal("0"),
            occurred_at=NOW,
        )
    )

    assert tx.cost_basis == Decimal("25000.00")
    assert tx.realized_pnl == Decimal("-1000.00")
    assert policy.quantity == Decimal("0.75000000")
    assert policy.total_cost == Decimal("75000.00")
    assert policy.active is True
    assert cash.quantity == Decimal("25000.00000000")

    service.reverse(tx.id, NOW, "領回比例輸入錯誤")
    assert policy.quantity == Decimal("1.00000000")
    assert policy.total_cost == Decimal("100000.00")
    assert cash.quantity == Decimal("1000.00000000")
