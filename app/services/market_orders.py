from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Trade
from app.schemas.trading import (
    BuyRequest,
    IntradayQuoteRead,
    MarketBuyRequest,
    MarketSellRequest,
    MarketStrategySellRequest,
    SellRequest,
    StrategySellRequest,
)
from app.services.ports import IntradayMarketDataPort
from app.services.trading import TradingService


class MarketOrderService:
    """以伺服器端最新行情執行 paper market order。"""

    def __init__(self, db: Session, market_data: IntradayMarketDataPort) -> None:
        self.db = db
        self.market_data = market_data

    def buy(self, request: MarketBuyRequest) -> Trade:
        quote = self._quote(request.symbol)
        return TradingService(self.db).buy(
            BuyRequest(
                symbol=request.symbol,
                name=quote.name,
                quantity=request.quantity,
                price=quote.price,
                stop_price=request.stop_price,
            )
        )

    def sell(self, request: MarketSellRequest) -> Trade:
        quote = self._quote(request.symbol)
        return TradingService(self.db).sell(
            SellRequest(symbol=request.symbol, quantity=request.quantity, price=quote.price)
        )

    def sell_next_424_stage(self, request: MarketStrategySellRequest) -> Trade:
        quote = self._quote(request.symbol)
        return TradingService(self.db).sell_next_424_stage(
            StrategySellRequest(symbol=request.symbol, price=quote.price)
        )

    def _quote(self, symbol: str) -> IntradayQuoteRead:
        quote = self.market_data.get_quote(symbol)
        if quote.symbol != symbol:
            raise HTTPException(status_code=502, detail="行情股票代號與委託不符")
        return quote
