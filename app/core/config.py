from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "自動化交易（模擬模式）"
    database_url: str = "postgresql+psycopg://trading:change-me@db:5432/trading"
    initial_capital: Decimal = Decimal("2000000")
    api_base_url: str = "http://localhost:8000"
    twse_api_url: str = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    market_data_timeout_seconds: float = 15.0
    market_data_stale_after_seconds: float = 10.0
    fugle_api_key: str = ""
    fugle_rest_url: str = "https://api.fugle.tw/marketdata/v1.0/stock"
    fugle_websocket_url: str = "wss://api.fugle.tw/marketdata/v1.0/stock/streaming"
    fugle_max_subscriptions: int = 5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
