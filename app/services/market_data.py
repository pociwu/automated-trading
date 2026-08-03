from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from threading import Lock
from time import monotonic

import httpx

from app.core.config import get_settings
from app.schemas.trading import IntradayQuoteRead, MarketQuoteRead, PriceLimitsRead


class MarketDataError(RuntimeError):
    pass


class FugleIntradayMarketDataProvider:
    """台股盤中最新成交價；資料來源為 Fugle MarketData REST API。"""

    source = "Fugle MarketData"

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = settings.fugle_api_key if api_key is None else api_key
        self.url = settings.fugle_rest_url.rstrip("/")
        self.client = client or httpx.Client(timeout=settings.market_data_timeout_seconds)

    def get_quote(self, symbol: str) -> IntradayQuoteRead:
        normalized = symbol.strip().upper()
        if not normalized:
            raise MarketDataError("股票代號不可空白")
        if not self.api_key:
            raise MarketDataError("FUGLE_API_KEY 尚未設定")
        try:
            response = self.client.get(
                f"{self.url}/intraday/quote/{normalized}",
                headers={"Accept": "application/json", "X-API-KEY": self.api_key},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketDataError(f"無法取得 {normalized} 即時行情") from exc
        if not isinstance(payload, dict):
            raise MarketDataError("Fugle 即時行情格式不正確")

        last_trade = payload.get("lastTrade") or {}
        if not isinstance(last_trade, dict):
            last_trade = {}
        price = self._decimal(last_trade.get("price", payload.get("lastPrice")), "最新成交價")
        raw_time = last_trade.get("time", payload.get("lastUpdated"))
        try:
            quoted_at = datetime.fromtimestamp(float(raw_time) / 1_000_000, UTC)
        except (OSError, OverflowError, TypeError, ValueError) as exc:
            raise MarketDataError(f"{normalized} 即時行情時間不正確") from exc
        return IntradayQuoteRead(
            symbol=str(payload.get("symbol") or normalized).strip().upper(),
            name=str(payload.get("name") or "").strip(),
            price=price,
            bid=self._optional_decimal(last_trade.get("bid")),
            ask=self._optional_decimal(last_trade.get("ask")),
            quoted_at=quoted_at,
            source=self.source,
        )

    def get_price_limits(self, symbol: str) -> PriceLimitsRead:
        normalized = symbol.strip().upper()
        if not normalized:
            raise MarketDataError("股票代號不可空白")
        if not self.api_key:
            raise MarketDataError("FUGLE_API_KEY 尚未設定")
        try:
            response = self.client.get(
                f"{self.url}/intraday/ticker/{normalized}",
                headers={"Accept": "application/json", "X-API-KEY": self.api_key},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketDataError(f"無法取得 {normalized} 漲跌停價格") from exc
        if not isinstance(payload, dict):
            raise MarketDataError("Fugle 股票基本資料格式不正確")
        return PriceLimitsRead(
            symbol=str(payload.get("symbol") or normalized).strip().upper(),
            reference_price=self._decimal(payload.get("referencePrice"), "參考價"),
            limit_down_price=self._decimal(payload.get("limitDownPrice"), "跌停價"),
            limit_up_price=self._decimal(payload.get("limitUpPrice"), "漲停價"),
        )

    @staticmethod
    def _decimal(value: object, label: str) -> Decimal:
        try:
            result = Decimal(str(value))
        except InvalidOperation as exc:
            raise MarketDataError(f"{label}不正確") from exc
        if not result.is_finite() or result <= 0:
            raise MarketDataError(f"{label}不正確")
        return result

    @classmethod
    def _optional_decimal(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return cls._decimal(value, "買賣價")


class TwseMarketDataProvider:
    """上市股票盤後收盤價；資料來源為臺灣證券交易所 OpenAPI。"""

    source = "TWSE OpenAPI"
    _cache: list[dict[str, str]] | None = None
    _cache_at: float = 0
    _lock = Lock()

    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self.url = settings.twse_api_url
        self.client = client or httpx.Client(timeout=settings.market_data_timeout_seconds)

    def get_close(self, symbol: str) -> MarketQuoteRead:
        normalized = symbol.strip().upper()
        row = next(
            (item for item in self._records() if item.get("Code", "").strip().upper() == normalized),
            None,
        )
        if row is None:
            raise MarketDataError(f"TWSE 找不到上市股票代號 {normalized}")
        raw_close = row.get("ClosingPrice", "").replace(",", "").strip()
        try:
            close = Decimal(raw_close)
        except InvalidOperation as exc:
            raise MarketDataError(f"{normalized} 今日沒有有效收盤價") from exc
        if close <= 0:
            raise MarketDataError(f"{normalized} 今日沒有有效收盤價")
        return MarketQuoteRead(
            symbol=normalized,
            name=row.get("Name", "").strip(),
            close=close,
            price_date=self._parse_date(row.get("Date", "")),
            source=self.source,
        )

    def _records(self) -> list[dict[str, str]]:
        # 官方端點一次回傳全部上市股票；短期快取避免每檔持股各下載一次。
        cls = type(self)
        with cls._lock:
            if cls._cache is not None and monotonic() - cls._cache_at < 300:
                return cls._cache
            try:
                response = self.client.get(self.url, headers={"Accept": "application/json"})
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise MarketDataError("無法取得 TWSE 收盤行情") from exc
            if not isinstance(payload, list):
                raise MarketDataError("TWSE 回傳格式不正確")
            cls._cache = payload
            cls._cache_at = monotonic()
            return payload

    @staticmethod
    def _parse_date(raw: str) -> date:
        digits = raw.strip().replace("/", "").replace("-", "")
        try:
            if len(digits) == 7:  # 民國年 YYYMMDD
                return date(int(digits[:3]) + 1911, int(digits[3:5]), int(digits[5:7]))
            if len(digits) == 8:
                return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError as exc:
            raise MarketDataError(f"TWSE 日期格式不正確：{raw}") from exc
        raise MarketDataError(f"TWSE 日期格式不正確：{raw}")
