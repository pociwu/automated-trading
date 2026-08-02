from datetime import UTC, datetime, timedelta
from math import isfinite

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import MarketDataStatus
from app.schemas.trading import MarketDataHealthRead


class MarketDataHealthService:
    def __init__(self, db: Session, now: datetime | None = None) -> None:
        self.db = db
        self.now = now or datetime.now(UTC).replace(tzinfo=None)

    def record_connected(self, subscribed_symbols: int, provider: str = "fugle") -> None:
        state = self._state(provider)
        state.connected = True
        state.subscribed_symbols = subscribed_symbols
        state.last_message_at = self.now
        state.detail = None
        state.updated_at = self.now
        self.db.commit()

    def record_disconnected(self, detail: str, provider: str = "fugle") -> None:
        state = self._state(provider)
        state.connected = False
        state.subscribed_symbols = 0
        state.detail = detail[:500]
        state.updated_at = self.now
        self.db.commit()

    def record_idle(self, provider: str = "fugle") -> None:
        state = self._state(provider)
        state.connected = False
        state.subscribed_symbols = 0
        state.detail = None
        state.updated_at = self.now
        self.db.commit()

    def record_message(self, provider: str = "fugle") -> None:
        state = self._state(provider)
        state.last_message_at = self.now
        state.updated_at = self.now
        self.db.commit()

    def record_tick(self, source_time: object, provider: str = "fugle") -> bool:
        state = self._state(provider)

        state.last_message_at = self.now
        state.updated_at = self.now
        try:
            microseconds = float(source_time)
            if not isfinite(microseconds):
                raise ValueError
            source_at = datetime.fromtimestamp(microseconds / 1_000_000, UTC).replace(tzinfo=None)
        except (OSError, OverflowError, TypeError, ValueError):
            state.detail = "Rejected market tick with invalid source time"
            self.db.commit()
            return False

        stale_after = timedelta(seconds=get_settings().market_data_stale_after_seconds)
        if abs(self.now - source_at) > stale_after:
            state.detail = "Rejected stale market tick"
            self.db.commit()
            return False

        state.last_tick_at = source_at
        state.detail = None
        self.db.commit()
        return True

    def _state(self, provider: str) -> MarketDataStatus:
        state = self.db.get(MarketDataStatus, provider)
        if state is None:
            state = MarketDataStatus(provider=provider, connected=False, subscribed_symbols=0)
            self.db.add(state)
        return state

    def read(self, provider: str = "fugle") -> MarketDataHealthRead:
        state = self.db.get(MarketDataStatus, provider)
        if state is None:
            return MarketDataHealthRead(
                provider=provider,
                status="unavailable",
                connected=False,
                subscribed_symbols=0,
                last_message_at=None,
                last_tick_at=None,
                stale=True,
                detail="Matcher has not reported status yet",
            )

        stale_after = timedelta(seconds=get_settings().market_data_stale_after_seconds)
        stale = state.last_tick_at is None or self.now - state.last_tick_at > stale_after
        if state.subscribed_symbols == 0 and state.detail is None:
            status = "idle"
            stale = False
        elif not state.connected:
            status = "unavailable"
        elif stale:
            status = "degraded"
        else:
            status = "healthy"
        return MarketDataHealthRead(
            provider=state.provider,
            status=status,
            connected=state.connected,
            subscribed_symbols=state.subscribed_symbols,
            last_message_at=state.last_message_at,
            last_tick_at=state.last_tick_at,
            stale=stale,
            detail=state.detail,
        )
