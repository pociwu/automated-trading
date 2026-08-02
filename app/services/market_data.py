from datetime import date
from decimal import Decimal, InvalidOperation
from threading import Lock
from time import monotonic

import httpx

from app.core.config import get_settings
from app.schemas.trading import MarketQuoteRead


class MarketDataError(RuntimeError):
    pass


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

