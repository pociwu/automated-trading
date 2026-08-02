from decimal import Decimal
from typing import Protocol

from app.schemas.trading import IntradayQuoteRead


class NotificationPort(Protocol):
    def trade_executed(self, message: str) -> None: ...


class BrokerPort(Protocol):
    def submit_order(self, symbol: str, quantity: int, price: Decimal) -> str: ...


class IntradayMarketDataPort(Protocol):
    def get_quote(self, symbol: str) -> IntradayQuoteRead: ...


class NullNotifier:
    def trade_executed(self, message: str) -> None:
        return None

