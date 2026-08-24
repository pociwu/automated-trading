import html
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.core.config import get_settings
from app.services.market_data import (
    FugleIntradayMarketDataProvider,
    MarketDataError,
    TwseMarketDataProvider,
)


CRYPTO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "USDC": "usd-coin",
    "LINK": "chainlink",
}


class PersonalAssetMarketDataProvider:
    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.market_data_timeout_seconds, follow_redirects=True)

    def gold_buy_price(self) -> tuple[Decimal, datetime, str]:
        response = self.client.get(self.settings.bot_gold_url, headers={"Accept": "text/html"})
        response.raise_for_status()
        text = self._visible_text(response.text)
        match = re.search(r"黃金存摺\s*本行賣出\s*[\d,.]+\s*本行買進\s*([\d,.]+)", text)
        if not match:
            raise MarketDataError("無法解析臺灣銀行黃金存摺買進價")
        return self._decimal(match.group(1)), self._bot_time(text), "臺灣銀行黃金存摺買進價"

    def fx_spot_buy_rates(self) -> tuple[dict[str, Decimal], datetime, str]:
        response = self.client.get(self.settings.bot_fx_url, headers={"Accept": "text/html"})
        response.raise_for_status()
        rates: dict[str, Decimal] = {}
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", response.text, flags=re.I | re.S):
            currency = re.search(r"\(([A-Z]{3})\)", self._visible_text(row))
            spot_cell = re.search(
                r'<td[^>]*data-table=["\']本行即期買入["\'][^>]*>(.*?)</td>',
                row,
                flags=re.I | re.S,
            )
            if currency and spot_cell:
                value = re.search(r'value=["\']([\d.]+)["\']', spot_cell.group(1), flags=re.I)
                raw = value.group(1) if value else self._visible_text(spot_cell.group(1))
                if raw and raw != "-":
                    rates[currency.group(1)] = self._decimal(raw)
        if not rates:
            raise MarketDataError("無法解析臺灣銀行即期買入匯率")
        return rates, self._bot_time(self._visible_text(response.text)), "臺灣銀行即期買入匯率"

    def crypto_twd_prices(self) -> tuple[dict[str, Decimal], datetime, str]:
        headers = {"Accept": "application/json"}
        if self.settings.coingecko_demo_api_key:
            headers["x-cg-demo-api-key"] = self.settings.coingecko_demo_api_key
        response = self.client.get(
            f"{self.settings.coingecko_api_url.rstrip('/')}/simple/price",
            params={
                "ids": ",".join(CRYPTO_IDS.values()),
                "vs_currencies": "twd",
                "include_last_updated_at": "true",
            },
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()
        prices: dict[str, Decimal] = {}
        updated = 0
        for symbol, coin_id in CRYPTO_IDS.items():
            row = payload.get(coin_id) or {}
            if row.get("twd") is not None:
                prices[symbol] = self._decimal(row["twd"])
                updated = max(updated, int(row.get("last_updated_at") or 0))
        if not prices:
            raise MarketDataError("CoinGecko 未回傳有效新臺幣價格")
        quoted_at = datetime.fromtimestamp(updated, UTC) if updated else datetime.now(UTC)
        return prices, quoted_at, "CoinGecko Demo API"

    def stock_price(self, symbol: str) -> tuple[Decimal, datetime, str, str]:
        try:
            quote = FugleIntradayMarketDataProvider().get_quote(symbol)
            return quote.price, quote.quoted_at, quote.source, quote.name
        except MarketDataError:
            quote = TwseMarketDataProvider(client=self.client).get_close(symbol)
            quoted_at = datetime.combine(quote.price_date, datetime.min.time(), tzinfo=UTC)
            return quote.close, quoted_at, quote.source, quote.name

    @staticmethod
    def _visible_text(raw: str) -> str:
        without_tags = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.I | re.S)
        without_tags = re.sub(r"<[^>]+>", " ", without_tags)
        return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()

    @staticmethod
    def _decimal(value: object) -> Decimal:
        try:
            result = Decimal(str(value).replace(",", "").strip())
        except InvalidOperation as exc:
            raise MarketDataError("行情價格格式不正確") from exc
        if not result.is_finite() or result <= 0:
            raise MarketDataError("行情價格必須大於零")
        return result

    @staticmethod
    def _bot_time(text: str) -> datetime:
        match = re.search(r"掛牌時間[：:]\s*(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", text)
        if not match:
            return datetime.now(UTC)
        from zoneinfo import ZoneInfo

        local = datetime(*(int(part) for part in match.groups()), tzinfo=ZoneInfo("Asia/Taipei"))
        return local.astimezone(UTC)
