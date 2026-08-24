from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import PersonalAssetAccount, PersonalAssetPosition, PersonalAssetSnapshot, PersonalAssetTransaction
from app.schemas.personal_assets import PersonalAssetPositionRead, PersonalAssetSnapshotRead, PersonalAssetType
from app.services.personal_asset_market_data import PersonalAssetMarketDataProvider
from app.services.personal_assets import money


CATEGORY_FIELDS = {
    PersonalAssetType.STOCK.value: "stock_value",
    PersonalAssetType.GOLD.value: "gold_value",
    PersonalAssetType.INSURANCE.value: "insurance_value",
    PersonalAssetType.TWD.value: "twd_value",
    PersonalAssetType.FX.value: "fx_value",
    PersonalAssetType.CRYPTO.value: "crypto_value",
}


class PersonalAssetValuationService:
    def __init__(self, db: Session, provider: PersonalAssetMarketDataProvider | None = None) -> None:
        self.db = db
        self.provider = provider or PersonalAssetMarketDataProvider()

    def refresh(self) -> tuple[int, list[str]]:
        positions = list(self.db.scalars(select(PersonalAssetPosition).where(PersonalAssetPosition.active)).all())
        updated = 0
        stale: list[str] = []
        gold = fx = crypto = None
        for position in positions:
            if position.asset_type in {PersonalAssetType.TWD.value, PersonalAssetType.INSURANCE.value}:
                continue
            try:
                if position.asset_type == PersonalAssetType.STOCK.value:
                    price, quoted_at, source, name = self.provider.stock_price(position.symbol)
                    position.name = name or position.name
                elif position.asset_type == PersonalAssetType.GOLD.value:
                    gold = gold or self.provider.gold_buy_price()
                    price, quoted_at, source = gold
                elif position.asset_type == PersonalAssetType.FX.value:
                    fx = fx or self.provider.fx_spot_buy_rates()
                    rates, quoted_at, source = fx
                    price = rates[position.symbol]
                elif position.asset_type == PersonalAssetType.CRYPTO.value:
                    crypto = crypto or self.provider.crypto_twd_prices()
                    prices, quoted_at, source = crypto
                    price = prices[position.symbol]
                else:
                    continue
                position.current_price_twd = price
                position.price_at = self._naive(quoted_at)
                position.price_source = source
                position.manual_price = False
                updated += 1
            except Exception as exc:  # provider/network errors retain last successful value
                stale.append(f"{position.symbol}: {exc}")
        self.db.commit()
        return updated, stale

    def set_manual_price(self, position_id: int, price: Decimal, quoted_at: datetime) -> PersonalAssetPosition:
        position = self.db.get(PersonalAssetPosition, position_id)
        if position is None:
            raise KeyError(position_id)
        position.current_price_twd = price
        position.price_at = self._naive(quoted_at)
        position.price_source = "手動備援"
        position.manual_price = True
        if position.asset_type == PersonalAssetType.INSURANCE.value:
            position.valuation_date = quoted_at.date()
        self.db.commit()
        self.db.refresh(position)
        return position

    def position_reads(self) -> list[PersonalAssetPositionRead]:
        accounts = {row.id: row for row in self.db.scalars(select(PersonalAssetAccount)).all()}
        positions = self.db.scalars(select(PersonalAssetPosition).where(PersonalAssetPosition.active).order_by(PersonalAssetPosition.asset_type, PersonalAssetPosition.id)).all()
        return [self._position_read(position, accounts[position.account_id]) for position in positions]

    def create_snapshot(self, scheduled_at: datetime) -> PersonalAssetSnapshot:
        scheduled = self._naive(scheduled_at)
        reads = self.position_reads()
        values = {field: Decimal("0") for field in CATEGORY_FIELDS.values()}
        stale_names: list[str] = []
        for row in reads:
            values[CATEGORY_FIELDS[row.asset_type]] += row.current_value
            if row.stale:
                stale_names.append(row.symbol)
        total = money(sum(values.values(), Decimal("0")))
        basis = money(sum((row.total_cost if row.asset_type != PersonalAssetType.TWD.value else row.current_value) for row in reads))
        snapshot = self.db.scalar(select(PersonalAssetSnapshot).where(PersonalAssetSnapshot.scheduled_at == scheduled))
        payload = {
            "total_value": total,
            "total_basis": basis,
            **{key: money(value) for key, value in values.items()},
            "stale": bool(stale_names),
            "stale_detail": ", ".join(stale_names),
        }
        if snapshot is None:
            snapshot = PersonalAssetSnapshot(scheduled_at=scheduled, **payload)
            self.db.add(snapshot)
        else:
            for key, value in payload.items():
                setattr(snapshot, key, value)
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def dashboard(self, days: int | None = 30) -> dict:
        reads = self.position_reads()
        total_value = money(sum((row.current_value for row in reads), Decimal("0")))
        total_basis = money(sum((row.current_value if row.asset_type == PersonalAssetType.TWD.value else row.total_cost for row in reads), Decimal("0")))
        query = select(PersonalAssetSnapshot)
        if days is not None:
            query = query.where(PersonalAssetSnapshot.scheduled_at >= datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days))
        snapshots = list(self.db.scalars(query.order_by(PersonalAssetSnapshot.scheduled_at)).all())
        latest = snapshots[-1] if snapshots else None
        has_backdated = False
        if latest:
            has_backdated = self.db.scalar(
                select(PersonalAssetTransaction.id).where(
                    PersonalAssetTransaction.created_at > latest.created_at,
                    PersonalAssetTransaction.occurred_at < latest.scheduled_at,
                ).limit(1)
            ) is not None
        return {
            "total_value": total_value,
            "total_basis": total_basis,
            "estimated_difference": money(total_value - total_basis),
            "stale_count": sum(row.stale for row in reads),
            "positions": reads,
            "snapshots": [PersonalAssetSnapshotRead.model_validate(row, from_attributes=True) for row in snapshots],
            "has_backdated_changes": has_backdated,
        }

    @staticmethod
    def _position_read(position: PersonalAssetPosition, account: PersonalAssetAccount) -> PersonalAssetPositionRead:
        price = position.current_price_twd
        value = money(position.quantity * price) if price is not None else Decimal("0")
        basis = value if position.asset_type == PersonalAssetType.TWD.value else money(position.total_cost)
        pnl = money(value - basis)
        average = money(position.total_cost / position.quantity) if position.quantity else Decimal("0")
        rate = money(pnl / basis * 100) if basis else Decimal("0")
        now = datetime.now(UTC).replace(tzinfo=None)
        if position.asset_type == PersonalAssetType.INSURANCE.value:
            stale = position.valuation_date is None or position.valuation_date < datetime.now().date() - timedelta(days=365)
        elif position.asset_type == PersonalAssetType.TWD.value:
            stale = False
        else:
            stale = position.price_at is None or position.price_at < now - timedelta(days=7)
        return PersonalAssetPositionRead(
            id=position.id,
            account_id=position.account_id,
            account_name=account.name,
            institution=account.institution,
            asset_type=position.asset_type,
            symbol=position.symbol,
            name=position.name,
            quantity=position.quantity,
            total_cost=position.total_cost,
            average_cost=average,
            current_price_twd=price,
            current_value=value,
            unrealized_pnl=pnl,
            return_rate=rate,
            price_source=position.price_source,
            price_at=position.price_at,
            stale=stale,
            valuation_date=position.valuation_date,
            policy_last4=position.policy_last4,
            policy_status=position.policy_status,
        )

    @staticmethod
    def _naive(value: datetime) -> datetime:
        return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value
