import asyncio
from decimal import Decimal, InvalidOperation
import json
import logging

from websockets.asyncio.client import connect

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.market_data_health import MarketDataHealthService
from app.services.orders import OrderService


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def pending_symbols() -> set[str]:
    with SessionLocal() as db:
        return OrderService(db).pending_symbols()


def record_connected(subscribed_symbols: int) -> None:
    with SessionLocal() as db:
        MarketDataHealthService(db).record_connected(subscribed_symbols)


def record_message() -> None:
    with SessionLocal() as db:
        MarketDataHealthService(db).record_message()


def record_disconnected(detail: str) -> None:
    with SessionLocal() as db:
        MarketDataHealthService(db).record_disconnected(detail)


def process_trade_tick(symbol: object, raw_price: object, source_time: object) -> bool:
    if not isinstance(symbol, str) or not symbol.strip():
        logger.warning("Rejected market tick without a symbol")
        return False
    try:
        price = Decimal(str(raw_price))
    except InvalidOperation:
        logger.warning("Rejected invalid market price: %s %s", symbol, raw_price)
        return False
    if not price.is_finite() or price <= 0:
        logger.warning("Rejected invalid market price: %s %s", symbol, raw_price)
        return False

    with SessionLocal() as db:
        if not MarketDataHealthService(db).record_tick(source_time):
            logger.warning("Rejected stale or invalid market tick: %s", symbol)
            return False
        trades = OrderService(db).process_tick(symbol, price)
        for trade in trades:
            logger.info("Filled limit order: %s %s @ %s", trade.symbol, trade.quantity, trade.price)
    return True


async def stream_once() -> None:
    settings = get_settings()
    symbols = pending_symbols()
    if not symbols:
        with SessionLocal() as db:
            MarketDataHealthService(db).record_idle()
        await asyncio.sleep(5)
        return

    async with connect(settings.fugle_websocket_url, ping_interval=20, ping_timeout=20) as websocket:
        await websocket.send(json.dumps({"event": "auth", "data": {"apikey": settings.fugle_api_key}}))
        while True:
            message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=15))
            if message.get("event") == "authenticated":
                record_connected(len(symbols))
                break
            if message.get("event") == "error":
                raise RuntimeError(message.get("data", {}).get("message", "Fugle authentication failed"))

        for symbol in sorted(symbols):
            await websocket.send(
                json.dumps({"event": "subscribe", "data": {"channel": "trades", "symbol": symbol}})
            )
        logger.info("Subscribed to market data: %s", ", ".join(sorted(symbols)))

        while True:
            try:
                raw_message = await asyncio.wait_for(websocket.recv(), timeout=5)
            except TimeoutError:
                if pending_symbols() != symbols:
                    return
                continue
            message = json.loads(raw_message)
            if message.get("event") == "data" and message.get("channel") == "trades":
                data = message.get("data", {})
                if not data.get("isTrial", False) and data.get("price") is not None:
                    process_trade_tick(data.get("symbol", ""), data["price"], data.get("time"))
            else:
                record_message()
            if pending_symbols() != symbols:
                return


async def run() -> None:
    settings = get_settings()
    if not settings.fugle_api_key:
        raise RuntimeError("FUGLE_API_KEY is required")
    while True:
        try:
            await stream_once()
        except Exception as exc:
            record_disconnected(str(exc))
            logger.exception("Market stream disconnected; retrying")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run())
