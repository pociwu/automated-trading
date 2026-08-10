from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import WatchlistItem
from app.services.trading import TradingService


class WatchlistService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_items(self) -> list[WatchlistItem]:
        account = TradingService(self.db).account()
        return list(
            self.db.scalars(
                select(WatchlistItem)
                .where(WatchlistItem.account_id == account.id)
                .order_by(WatchlistItem.created_at, WatchlistItem.id)
            ).all()
        )

    def add(self, symbol: str, name: str) -> WatchlistItem:
        account = TradingService(self.db).account()
        item = WatchlistItem(account_id=account.id, symbol=symbol, name=name)
        self.db.add(item)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=400, detail="此股票已在觀察清單") from exc
        self.db.refresh(item)
        return item

    def remove(self, symbol: str) -> None:
        account = TradingService(self.db).account()
        normalized = symbol.strip().upper()
        item = self.db.scalar(
            select(WatchlistItem).where(
                WatchlistItem.account_id == account.id,
                WatchlistItem.symbol == normalized,
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="觀察清單中找不到此股票")
        self.db.delete(item)
        self.db.commit()
