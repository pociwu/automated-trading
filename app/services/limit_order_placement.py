from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import LimitOrder
from app.schemas.trading import LimitOrderCreate
from app.services.orders import OrderService
from app.services.ports import LimitOrderMarketDataPort


class LimitOrderPlacementService:
    """使用伺服器端行情驗證並建立 paper limit order。"""

    def __init__(self, db: Session, market_data: LimitOrderMarketDataPort) -> None:
        self.db = db
        self.market_data = market_data

    def place(self, request: LimitOrderCreate) -> LimitOrder:
        quote = self.market_data.get_quote(request.symbol)
        limits = self.market_data.get_price_limits(request.symbol)
        if quote.symbol != request.symbol or limits.symbol != request.symbol:
            raise HTTPException(status_code=502, detail="行情股票代號與委託不符")
        if not limits.limit_down_price <= request.limit_price <= limits.limit_up_price:
            lower = self._display_price(limits.limit_down_price)
            upper = self._display_price(limits.limit_up_price)
            raise HTTPException(
                status_code=400,
                detail=f"限價必須介於跌停價 {lower} 與漲停價 {upper} 之間",
            )
        normalized = request.model_copy(update={"name": request.name or quote.name})
        return OrderService(self.db).place(normalized)

    @staticmethod
    def _display_price(value: Decimal) -> str:
        return format(value.normalize(), "f")
