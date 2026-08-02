from decimal import Decimal
from typing import Protocol


class NotificationPort(Protocol):
    def trade_executed(self, message: str) -> None: ...


class BrokerPort(Protocol):
    def submit_order(self, symbol: str, quantity: int, price: Decimal) -> str: ...


class NullNotifier:
    def trade_executed(self, message: str) -> None:
        return None


