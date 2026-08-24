from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrades_empty_database_to_complete_schema(tmp_path: Path):
    database_path = tmp_path / "migration.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")

    command.upgrade(config, "head")

    tables = set(inspect(create_engine(f"sqlite:///{database_path.as_posix()}")).get_table_names())
    assert tables == {
        "accounts",
        "alembic_version",
        "holdings",
        "limit_orders",
        "market_data_status",
        "price_history",
        "trades",
        "watchlist_items",
        "personal_asset_accounts",
        "personal_asset_positions",
        "personal_asset_transactions",
        "personal_asset_snapshots",
    }
    command.check(config)
