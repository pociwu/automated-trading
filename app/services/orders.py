from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Account, Holding, LimitOrder, OrderStatus, Trade, TradeReason, TradeSide
from app.schemas.trading import BuyRequest, LimitOrderCreate, SellRequest
from app.services.trading import TradingService, money


class OrderService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_orders(self, status: OrderStatus | None = None, limit: int = 200) -> list[LimitOrder]:
        account = TradingService(self.db).account()
        query = select(LimitOrder).where(LimitOrder.account_id == account.id)
        if status is not None:
            query = query.where(LimitOrder.status == status)
        return list(self.db.scalars(query.order_by(LimitOrder.placed_at.desc()).limit(limit)).all())

    def place(self, request: LimitOrderCreate) -> LimitOrder:
        trading = TradingService(self.db)
        account = trading.account()
        pending_symbols = set(
            self.db.scalars(
                select(LimitOrder.symbol)
                .where(LimitOrder.account_id == account.id, LimitOrder.status == OrderStatus.PENDING)
                .distinct()
            ).all()
        )
        if request.symbol not in pending_symbols and len(pending_symbols) >= get_settings().fugle_max_subscriptions:
            raise HTTPException(status_code=400, detail="即時行情訂閱股票數已達設定上限")

        if request.side == TradeSide.BUY:
            required_cash = money(request.limit_price * request.quantity)
            if required_cash > account.cash - account.reserved_cash:
                raise HTTPException(status_code=400, detail="可用現金不足以掛單")
            holding = self._holding(account, request.symbol)
            if holding and holding.sell_stage > 0:
                raise HTTPException(status_code=400, detail="4:2:4 賣出已開始，不能再掛買單")
            account.reserved_cash = money(account.reserved_cash + required_cash)
        else:
            holding = self._holding(account, request.symbol)
            if holding is None or request.quantity > holding.quantity - holding.reserved_quantity:
                raise HTTPException(status_code=400, detail="可用持股不足以掛單")
            holding.reserved_quantity += request.quantity

        order = LimitOrder(
            account_id=account.id,
            symbol=request.symbol,
            name=request.name,
            side=request.side,
            quantity=request.quantity,
            limit_price=request.limit_price,
            status=OrderStatus.PENDING,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def cancel(self, order_id: int) -> LimitOrder:
        account = TradingService(self.db).account()
        order = self.db.scalar(
            select(LimitOrder)
            .where(LimitOrder.id == order_id, LimitOrder.account_id == account.id)
            .with_for_update()
        )
        if order is None:
            raise HTTPException(status_code=404, detail="找不到委託單")
        if order.status != OrderStatus.PENDING:
            raise HTTPException(status_code=400, detail="只有等待中的委託可以取消")
        self._release_reservation(account, order)
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = datetime.now()
        self.db.commit()
        self.db.refresh(order)
        return order

    def process_tick(self, symbol: str, price: Decimal) -> list[Trade]:
        normalized = symbol.strip().upper()
        trading = TradingService(self.db)
        trading.process_intraday_tick(normalized, price)
        account = trading.account()
        orders = self.db.scalars(
            select(LimitOrder)
            .where(
                LimitOrder.account_id == account.id,
                LimitOrder.symbol == normalized,
                LimitOrder.status == OrderStatus.PENDING,
            )
            .order_by(LimitOrder.placed_at, LimitOrder.id)
            .with_for_update(skip_locked=True)
        ).all()
        trades: list[Trade] = []
        for order in orders:
            matches = (
                order.side == TradeSide.BUY and price <= order.limit_price
            ) or (
                order.side == TradeSide.SELL and price >= order.limit_price
            )
            if not matches:
                continue
            self._release_reservation(account, order)
            if order.side == TradeSide.BUY:
                trade = trading.buy(
                    BuyRequest(
                        symbol=order.symbol,
                        name=order.name,
                        quantity=order.quantity,
                        price=order.limit_price,
                    ),
                    reason=TradeReason.LIMIT_ORDER,
                    commit=False,
                )
            else:
                trade = trading.sell(
                    SellRequest(symbol=order.symbol, quantity=order.quantity, price=order.limit_price),
                    reason=TradeReason.LIMIT_ORDER,
                    commit=False,
                )
            order.status = OrderStatus.FILLED
            order.filled_price = order.limit_price
            order.trade_id = trade.id
            order.filled_at = datetime.now()
            trades.append(trade)
        holding = self._holding(account, normalized)
        if holding is not None:
            holding.last_price = price
            holding.updated_at = datetime.now()
        self.db.commit()
        for trade in trades:
            self.db.refresh(trade)
        return trades

    def pending_symbols(self) -> set[str]:
        account = TradingService(self.db).account()
        return set(
            self.db.scalars(
                select(LimitOrder.symbol)
                .where(LimitOrder.account_id == account.id, LimitOrder.status == OrderStatus.PENDING)
                .distinct()
            ).all()
        )

    def _holding(self, account: Account, symbol: str) -> Holding | None:
        return self.db.scalar(
            select(Holding).where(Holding.account_id == account.id, Holding.symbol == symbol)
        )

    def _release_reservation(self, account: Account, order: LimitOrder) -> None:
        if order.side == TradeSide.BUY:
            account.reserved_cash = money(account.reserved_cash - order.limit_price * order.quantity)
            return
        holding = self._holding(account, order.symbol)
        if holding is not None:
            holding.reserved_quantity -= order.quantity

