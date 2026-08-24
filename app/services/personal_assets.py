from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    PersonalAssetAccount,
    PersonalAssetPosition,
    PersonalAssetSnapshot,
    PersonalAssetTransaction,
)
from app.schemas.personal_assets import (
    PersonalAssetAccountCreate,
    PersonalAssetOpeningCreate,
    PersonalAssetType,
    PersonalAssetTransactionCreate,
    PersonalTransactionKind,
)


MONEY = Decimal("0.01")
QTY = Decimal("0.00000001")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def quantity(value: Decimal) -> Decimal:
    return value.quantize(QTY, rounding=ROUND_HALF_UP)


class PersonalAssetService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_account(self, request: PersonalAssetAccountCreate) -> PersonalAssetAccount:
        account = PersonalAssetAccount(**request.model_dump(mode="json"))
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def accounts(self) -> list[PersonalAssetAccount]:
        return list(self.db.scalars(select(PersonalAssetAccount).where(PersonalAssetAccount.active).order_by(PersonalAssetAccount.id)).all())

    def opening(self, request: PersonalAssetOpeningCreate) -> PersonalAssetPosition:
        if self._naive_utc(request.occurred_at) > datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=1):
            raise HTTPException(status_code=400, detail="期初日期不可位於未來")
        account = self._account(request.account_id)
        if account.asset_type != request.asset_type.value:
            raise HTTPException(status_code=400, detail="資產帳戶類型與部位不符")
        existing = self.db.scalar(
            select(PersonalAssetPosition).where(
                PersonalAssetPosition.account_id == account.id,
                PersonalAssetPosition.asset_type == request.asset_type.value,
                PersonalAssetPosition.symbol == request.symbol,
            )
        )
        if existing is not None and existing.active:
            raise HTTPException(status_code=400, detail="此帳戶已有相同部位，請使用資產異動")
        current_price = self._opening_price(request)
        position = existing or PersonalAssetPosition(
            account_id=account.id, asset_type=request.asset_type.value, symbol=request.symbol
        )
        position.name = request.name
        position.quantity = quantity(request.quantity)
        position.total_cost = money(request.total_cost)
        position.current_price_twd = current_price
        position.price_source = "期初手動估值" if current_price is not None else None
        position.price_at = self._naive_utc(request.occurred_at) if current_price is not None else None
        position.manual_price = current_price is not None
        position.valuation_date = request.valuation_date
        position.policy_last4 = request.policy_last4
        position.policy_status = request.policy_status
        position.active = True
        if request.asset_type == PersonalAssetType.TWD:
            position.current_price_twd = Decimal("1")
            position.total_cost = money(request.quantity)
            position.price_source = "帳面餘額"
        self.db.add(position)
        self.db.flush()
        self.db.add(
            PersonalAssetTransaction(
                kind=PersonalTransactionKind.OPENING.value,
                target_position_id=position.id,
                quantity=position.quantity,
                gross_amount=position.total_cost,
                fees=Decimal("0"),
                net_amount=position.total_cost,
                cost_basis=position.total_cost,
                realized_pnl=Decimal("0"),
                occurred_at=self._naive_utc(request.occurred_at),
                note=request.note,
            )
        )
        self.db.commit()
        self.db.refresh(position)
        return position

    def transact(self, request: PersonalAssetTransactionCreate) -> PersonalAssetTransaction:
        if self._naive_utc(request.occurred_at) > datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=1):
            raise HTTPException(status_code=400, detail="資產異動時間不可位於未來")
        source = self._position(request.source_position_id) if request.source_position_id else None
        target = self._position(request.target_position_id) if request.target_position_id else None
        kind = request.kind
        qty = quantity(request.quantity)
        gross = money(request.gross_amount)
        fees = money(request.fees)
        net = Decimal("0")
        basis = Decimal("0")
        pnl = Decimal("0")

        if kind == PersonalTransactionKind.BUY:
            self._require_twd(source)
            self._require_investment(target)
            outflow = money(gross + fees)
            self._debit_cash(source, outflow)
            target.quantity = quantity(target.quantity + qty)
            target.total_cost = money(target.total_cost + outflow)
            net = outflow
            basis = outflow
        elif kind == PersonalTransactionKind.SELL:
            self._require_investment(source)
            self._require_twd(target)
            self._require_quantity(source, qty)
            net = money(gross - fees)
            if net < 0:
                raise HTTPException(status_code=400, detail="費稅不可超過成交總額")
            basis = money(source.total_cost * qty / source.quantity)
            source.quantity = quantity(source.quantity - qty)
            source.total_cost = money(source.total_cost - basis)
            self._credit_cash(target, net)
            pnl = money(net - basis)
        elif kind == PersonalTransactionKind.TRANSFER:
            if source is None or target is None or source.asset_type != target.asset_type or source.symbol != target.symbol:
                raise HTTPException(status_code=400, detail="內部移轉的資產類型與代號必須相同")
            self._require_quantity(source, qty)
            basis = money(source.total_cost * qty / source.quantity) if source.quantity else Decimal("0")
            source.quantity = quantity(source.quantity - qty)
            source.total_cost = money(source.total_cost - basis)
            target.quantity = quantity(target.quantity + qty)
            target.total_cost = money(target.total_cost + basis + fees)
            net = basis
        elif kind == PersonalTransactionKind.EXTERNAL_IN:
            self._require_twd(target)
            self._credit_cash(target, gross)
            net = gross
            basis = gross
        elif kind == PersonalTransactionKind.EXTERNAL_OUT:
            self._require_twd(source)
            net = money(gross + fees)
            self._debit_cash(source, net)
            basis = net
        elif kind == PersonalTransactionKind.PREMIUM:
            self._require_twd(source)
            if target is None or target.asset_type != PersonalAssetType.INSURANCE.value:
                raise HTTPException(status_code=400, detail="保費目標必須是保單")
            outflow = money(gross + fees)
            self._debit_cash(source, outflow)
            target.total_cost = money(target.total_cost + outflow)
            net = outflow
            basis = outflow
        elif kind == PersonalTransactionKind.SURRENDER:
            if source is None or source.asset_type != PersonalAssetType.INSURANCE.value:
                raise HTTPException(status_code=400, detail="領回來源必須是保單")
            self._require_twd(target)
            self._require_quantity(source, qty)
            net = money(gross - fees)
            if net < 0:
                raise HTTPException(status_code=400, detail="費稅不可超過領回總額")
            self._credit_cash(target, net)
            basis = money(source.total_cost * qty / source.quantity)
            pnl = money(net - basis)
            source.quantity = quantity(source.quantity - qty)
            source.total_cost = money(source.total_cost - basis)
            if source.quantity == 0:
                source.policy_status = "SURRENDERED"
                source.active = False
        else:
            raise HTTPException(status_code=400, detail="不支援此資產異動類型")

        transaction = PersonalAssetTransaction(
            kind=kind.value,
            source_position_id=source.id if source else None,
            target_position_id=target.id if target else None,
            quantity=qty,
            gross_amount=gross,
            fees=fees,
            net_amount=net,
            cost_basis=basis,
            realized_pnl=pnl,
            occurred_at=self._naive_utc(request.occurred_at),
            note=request.note,
        )
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        return transaction

    def reverse(self, transaction_id: int, occurred_at: datetime, reason: str) -> PersonalAssetTransaction:
        original = self.db.get(PersonalAssetTransaction, transaction_id)
        if original is None:
            raise HTTPException(status_code=404, detail="找不到資產異動")
        if original.kind == PersonalTransactionKind.REVERSAL.value:
            raise HTTPException(status_code=400, detail="此異動不可沖銷")
        if original.reversed_at is not None:
            raise HTTPException(status_code=400, detail="此異動已沖銷")
        now = self._naive_utc(occurred_at)
        if now > datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=1):
            raise HTTPException(status_code=400, detail="沖銷日期不可位於未來")
        if original.kind == PersonalTransactionKind.OPENING.value:
            linked = self.db.scalar(
                select(PersonalAssetTransaction.id).where(
                    PersonalAssetTransaction.id != original.id,
                    PersonalAssetTransaction.kind != PersonalTransactionKind.REVERSAL.value,
                    PersonalAssetTransaction.reversed_at.is_(None),
                    (PersonalAssetTransaction.source_position_id == original.target_position_id)
                    | (PersonalAssetTransaction.target_position_id == original.target_position_id),
                ).limit(1)
            )
            if linked is not None:
                raise HTTPException(status_code=400, detail="此期初部位已有後續異動，請先由最新一筆逐筆沖銷")
        source = self._position(original.source_position_id) if original.source_position_id else None
        target = self._position(original.target_position_id) if original.target_position_id else None
        self._apply_inverse(original, source, target)
        original.reversed_at = now
        reversal = PersonalAssetTransaction(
            kind=PersonalTransactionKind.REVERSAL.value,
            source_position_id=original.target_position_id,
            target_position_id=original.source_position_id,
            quantity=original.quantity,
            gross_amount=original.gross_amount,
            fees=original.fees,
            net_amount=-original.net_amount,
            cost_basis=-original.cost_basis,
            realized_pnl=-original.realized_pnl,
            occurred_at=now,
            note=reason,
            reversal_of_id=original.id,
        )
        self.db.add(reversal)
        self.db.commit()
        self.db.refresh(reversal)
        return reversal

    def positions(self) -> list[PersonalAssetPosition]:
        return list(self.db.scalars(select(PersonalAssetPosition).where(PersonalAssetPosition.active).order_by(PersonalAssetPosition.asset_type, PersonalAssetPosition.id)).all())

    def transactions(self, limit: int = 500) -> list[PersonalAssetTransaction]:
        return list(self.db.scalars(select(PersonalAssetTransaction).order_by(PersonalAssetTransaction.occurred_at.desc(), PersonalAssetTransaction.id.desc()).limit(limit)).all())

    def snapshots(self, since: datetime | None = None) -> list[PersonalAssetSnapshot]:
        query = select(PersonalAssetSnapshot)
        if since is not None:
            query = query.where(PersonalAssetSnapshot.scheduled_at >= self._naive_utc(since))
        return list(self.db.scalars(query.order_by(PersonalAssetSnapshot.scheduled_at)).all())

    def _apply_inverse(self, tx: PersonalAssetTransaction, source: PersonalAssetPosition | None, target: PersonalAssetPosition | None) -> None:
        kind = PersonalTransactionKind(tx.kind)
        if kind == PersonalTransactionKind.OPENING:
            self._require_quantity(target, tx.quantity)
            target.quantity = Decimal("0")
            target.total_cost = Decimal("0")
            target.active = False
        elif kind == PersonalTransactionKind.BUY:
            self._require_quantity(target, tx.quantity)
            target.quantity = quantity(target.quantity - tx.quantity)
            target.total_cost = money(target.total_cost - tx.cost_basis)
            self._credit_cash(source, tx.net_amount)
        elif kind == PersonalTransactionKind.SELL:
            self._debit_cash(target, tx.net_amount)
            source.active = True
            source.quantity = quantity(source.quantity + tx.quantity)
            source.total_cost = money(source.total_cost + tx.cost_basis)
        elif kind == PersonalTransactionKind.TRANSFER:
            self._require_quantity(target, tx.quantity)
            target.quantity = quantity(target.quantity - tx.quantity)
            target.total_cost = money(target.total_cost - tx.cost_basis - tx.fees)
            source.quantity = quantity(source.quantity + tx.quantity)
            source.total_cost = money(source.total_cost + tx.cost_basis)
        elif kind == PersonalTransactionKind.EXTERNAL_IN:
            self._debit_cash(target, tx.net_amount)
        elif kind == PersonalTransactionKind.EXTERNAL_OUT:
            self._credit_cash(source, tx.net_amount)
        elif kind == PersonalTransactionKind.PREMIUM:
            target.total_cost = money(target.total_cost - tx.cost_basis)
            self._credit_cash(source, tx.net_amount)
        elif kind == PersonalTransactionKind.SURRENDER:
            self._debit_cash(target, tx.net_amount)
            source.active = True
            source.quantity = quantity(source.quantity + tx.quantity)
            source.total_cost = money(source.total_cost + tx.cost_basis)
            source.policy_status = "ACTIVE"

    @staticmethod
    def _opening_price(request: PersonalAssetOpeningCreate) -> Decimal | None:
        if request.current_value is None:
            return None
        return request.current_value if request.asset_type == PersonalAssetType.INSURANCE else request.current_value / request.quantity

    def _account(self, account_id: int) -> PersonalAssetAccount:
        account = self.db.get(PersonalAssetAccount, account_id)
        if account is None or not account.active:
            raise HTTPException(status_code=404, detail="找不到資產帳戶")
        return account

    def _position(self, position_id: int | None) -> PersonalAssetPosition:
        position = self.db.get(PersonalAssetPosition, position_id)
        if position is None:
            raise HTTPException(status_code=404, detail="找不到資產部位")
        return position

    @staticmethod
    def _require_twd(position: PersonalAssetPosition | None) -> None:
        if position is None or position.asset_type != PersonalAssetType.TWD.value:
            raise HTTPException(status_code=400, detail="此異動需要新臺幣銀行帳戶")

    @staticmethod
    def _require_investment(position: PersonalAssetPosition | None) -> None:
        if position is None or position.asset_type in {PersonalAssetType.TWD.value, PersonalAssetType.INSURANCE.value}:
            raise HTTPException(status_code=400, detail="此異動需要可交易資產部位")

    @staticmethod
    def _require_quantity(position: PersonalAssetPosition | None, amount: Decimal) -> None:
        if position is None or amount <= 0 or position.quantity < amount:
            raise HTTPException(status_code=400, detail="資產數量不足")

    @staticmethod
    def _debit_cash(position: PersonalAssetPosition | None, amount: Decimal) -> None:
        PersonalAssetService._require_twd(position)
        if position.quantity < amount:
            raise HTTPException(status_code=400, detail="銀行帳戶餘額不足")
        position.quantity = quantity(position.quantity - amount)
        position.total_cost = money(position.quantity)

    @staticmethod
    def _credit_cash(position: PersonalAssetPosition | None, amount: Decimal) -> None:
        PersonalAssetService._require_twd(position)
        position.quantity = quantity(position.quantity + amount)
        position.total_cost = money(position.quantity)

    @staticmethod
    def _naive_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)
