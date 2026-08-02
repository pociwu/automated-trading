from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Account, Holding, LimitOrder, OrderStatus, PriceHistory, Trade, TradeReason, TradeSide
from app.schemas.trading import (
    BuyRequest,
    DashboardRead,
    HoldingRead,
    PriceUpdateRequest,
    PriceUpdateResult,
    SellRequest,
    StrategySellRequest,
)
from app.services.ports import NullNotifier, NotificationPort
from app.services.strategy import ZhongDadan424Strategy


MONEY = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


class TradingService:
    def __init__(
        self,
        db: Session,
        strategy: ZhongDadan424Strategy | None = None,
        notifier: NotificationPort | None = None,
    ) -> None:
        self.db = db
        self.strategy = strategy or ZhongDadan424Strategy()
        self.notifier = notifier or NullNotifier()

    def account(self) -> Account:
        account = self.db.scalar(select(Account).where(Account.name == "main"))
        if account is None:
            raise HTTPException(status_code=500, detail="交易帳戶尚未初始化")
        return account

    def buy(
        self,
        request: BuyRequest,
        reason: TradeReason = TradeReason.MANUAL_BUY,
        commit: bool = True,
    ) -> Trade:
        account = self.account()
        amount = money(request.price * request.quantity)
        if amount > account.cash - account.reserved_cash:
            raise HTTPException(status_code=400, detail="可用現金餘額不足")
        holding = self.db.scalar(
            select(Holding).where(Holding.account_id == account.id, Holding.symbol == request.symbol)
        )

        if holding is None:
            holding = Holding(
                account_id=account.id,
                symbol=request.symbol,
                name=request.name,
                quantity=request.quantity,
                average_cost=request.price,
                last_price=request.price,
                stop_price=request.stop_price,
                sell_stage=0,
            )
            self.db.add(holding)
        else:
            if holding.sell_stage > 0:
                raise HTTPException(status_code=400, detail="4:2:4 賣出已開始，請完成出場後再重新買進")
            total_cost = holding.average_cost * holding.quantity + amount
            holding.quantity += request.quantity
            holding.average_cost = total_cost / holding.quantity
            holding.last_price = request.price
            holding.name = request.name or holding.name
            if request.stop_price is not None:
                holding.stop_price = request.stop_price

        account.cash = money(account.cash - amount)
        trade = Trade(
            account_id=account.id,
            symbol=request.symbol,
            name=request.name,
            side=TradeSide.BUY,
            quantity=request.quantity,
            price=request.price,
            amount=amount,
            reason=reason,
            stage=None,
        )
        self.db.add(trade)
        if commit:
            self.db.commit()
            self.db.refresh(trade)
            self.notifier.trade_executed(f"買進 {request.symbol} {request.quantity} 股")
        else:
            self.db.flush()
        return trade

    def sell_next_424_stage(self, request: StrategySellRequest) -> Trade:
        account = self.account()
        holding = self.db.scalar(
            select(Holding).where(Holding.account_id == account.id, Holding.symbol == request.symbol)
        )
        if holding is None:
            raise HTTPException(status_code=404, detail="找不到持股")
        has_pending_order = self.db.scalar(
            select(LimitOrder.id).where(
                LimitOrder.account_id == account.id,
                LimitOrder.symbol == request.symbol,
                LimitOrder.status == OrderStatus.PENDING,
            ).limit(1)
        )
        if has_pending_order is not None:
            raise HTTPException(status_code=400, detail="請先取消此股票的等待中委託")
        next_stage = holding.sell_stage + 1
        if next_stage > 3:
            raise HTTPException(status_code=400, detail="4:2:4 賣出已完成")
        base_quantity = holding.strategy_base_quantity or holding.quantity
        remaining_stages = 4 - next_stage
        if holding.quantity < remaining_stages:
            raise HTTPException(status_code=400, detail="剩餘股數不足以完成 4:2:4 分段賣出")
        quantity = self.strategy.sell_quantity(base_quantity, holding.quantity, next_stage)
        holding.strategy_base_quantity = base_quantity
        holding.sell_stage = next_stage
        self.db.flush()
        trade = self.sell(
            SellRequest(symbol=request.symbol, quantity=quantity, price=request.price),
            TradeReason.STRATEGY_424,
            commit=False,
        )
        trade.stage = next_stage
        self.db.commit()
        self.db.refresh(trade)
        return trade

    def sell(
        self,
        request: SellRequest,
        reason: TradeReason = TradeReason.MANUAL_SELL,
        commit: bool = True,
    ) -> Trade:
        account = self.account()
        holding = self.db.scalar(
            select(Holding).where(Holding.account_id == account.id, Holding.symbol == request.symbol)
        )
        if holding is None or holding.quantity - holding.reserved_quantity < request.quantity:
            raise HTTPException(status_code=400, detail="可用持股數量不足")

        amount = money(request.price * request.quantity)
        realized_pnl = money((request.price - holding.average_cost) * request.quantity)
        holding.quantity -= request.quantity
        holding.last_price = request.price
        account.cash = money(account.cash + amount)
        trade = Trade(
            account_id=account.id,
            symbol=holding.symbol,
            name=holding.name,
            side=TradeSide.SELL,
            quantity=request.quantity,
            price=request.price,
            amount=amount,
            realized_pnl=realized_pnl,
            reason=reason,
        )
        self.db.add(trade)
        if holding.quantity == 0:
            self.db.delete(holding)
        if commit:
            self.db.commit()
            self.db.refresh(trade)
            self.notifier.trade_executed(f"賣出 {request.symbol} {request.quantity} 股")
        else:
            self.db.flush()
        return trade

    def update_price(self, request: PriceUpdateRequest) -> PriceUpdateResult:
        account = self.account()
        existing = self.db.scalar(
            select(PriceHistory).where(
                PriceHistory.symbol == request.symbol,
                PriceHistory.price_date == request.price_date,
            )
        )
        if existing:
            existing.close = request.close
        else:
            self.db.add(PriceHistory(symbol=request.symbol, close=request.close, price_date=request.price_date))

        holding = self.db.scalar(
            select(Holding).where(Holding.account_id == account.id, Holding.symbol == request.symbol)
        )
        if holding is None:
            self.db.commit()
            return PriceUpdateResult(symbol=request.symbol, close=request.close, stopped_out=False)

        holding.last_price = request.close
        holding.updated_at = datetime.now()
        should_stop = self.strategy.should_stop(request.close, holding.stop_price)
        quantity = holding.quantity
        self.db.commit()
        if should_stop:
            self._cancel_pending_orders(request.symbol)
            trade = self.sell(
                SellRequest(symbol=request.symbol, quantity=quantity, price=request.close),
                TradeReason.S_POINT_STOP,
            )
            return PriceUpdateResult(
                symbol=request.symbol,
                close=request.close,
                stopped_out=True,
                stop_trade=trade,
            )
        return PriceUpdateResult(symbol=request.symbol, close=request.close, stopped_out=False)

    def process_intraday_tick(self, symbol: str, price: Decimal) -> Trade | None:
        account = self.account()
        holding = self.db.scalar(
            select(Holding).where(Holding.account_id == account.id, Holding.symbol == symbol)
        )
        if holding is None:
            return None
        holding.last_price = price
        holding.updated_at = datetime.now()
        if not self.strategy.should_stop(price, holding.stop_price):
            self.db.commit()
            return None
        quantity = holding.quantity
        self._cancel_pending_orders(symbol)
        return self.sell(
            SellRequest(symbol=symbol, quantity=quantity, price=price),
            TradeReason.S_POINT_STOP,
        )

    def _cancel_pending_orders(self, symbol: str) -> None:
        account = self.account()
        orders = self.db.scalars(
            select(LimitOrder).where(
                LimitOrder.account_id == account.id,
                LimitOrder.symbol == symbol,
                LimitOrder.status == OrderStatus.PENDING,
            )
        ).all()
        holding = self.db.scalar(
            select(Holding).where(Holding.account_id == account.id, Holding.symbol == symbol)
        )
        now = datetime.now()
        for order in orders:
            if order.side == TradeSide.BUY:
                account.reserved_cash = money(account.reserved_cash - order.limit_price * order.quantity)
            elif holding:
                holding.reserved_quantity -= order.quantity
            order.status = OrderStatus.CANCELLED
            order.cancelled_at = now
        self.db.flush()

    def dashboard(self) -> DashboardRead:
        account = self.account()
        holdings = self.db.scalars(
            select(Holding).where(Holding.account_id == account.id).order_by(Holding.symbol)
        ).all()
        rows: list[HoldingRead] = []
        holdings_cost = Decimal("0")
        market_value = Decimal("0")
        for holding in holdings:
            cost = holding.average_cost * holding.quantity
            value = holding.last_price * holding.quantity
            pnl = value - cost
            rows.append(
                HoldingRead(
                    symbol=holding.symbol,
                    name=holding.name,
                    quantity=holding.quantity,
                    average_cost=holding.average_cost,
                    last_price=holding.last_price,
                    stop_price=holding.stop_price,
                    sell_stage=holding.sell_stage,
                    reserved_quantity=holding.reserved_quantity,
                    available_quantity=holding.quantity - holding.reserved_quantity,
                    market_value=money(value),
                    unrealized_pnl=money(pnl),
                    return_rate=money(pnl / cost * 100) if cost else Decimal("0"),
                )
            )
            holdings_cost += cost
            market_value += value

        total_assets = account.cash + market_value
        total_pnl = total_assets - account.initial_capital
        return DashboardRead(
            initial_capital=account.initial_capital,
            cash=money(account.cash),
            reserved_cash=money(account.reserved_cash),
            available_cash=money(account.cash - account.reserved_cash),
            holdings_cost=money(holdings_cost),
            market_value=money(market_value),
            total_assets=money(total_assets),
            total_pnl=money(total_pnl),
            return_rate=money(total_pnl / account.initial_capital * 100),
            holdings=rows,
        )

