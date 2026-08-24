import logging
from datetime import datetime
from time import sleep
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.personal_asset_valuation import PersonalAssetValuationService


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
TAIPEI = ZoneInfo("Asia/Taipei")


def run() -> None:
    settings = get_settings()
    slots = {value.strip() for value in settings.personal_asset_snapshot_times.split(",") if value.strip()}
    last_slot: str | None = None
    logger.info("personal asset snapshot scheduler started slots=%s", sorted(slots))
    while True:
        now = datetime.now(TAIPEI)
        slot = now.strftime("%Y-%m-%d %H:%M")
        if now.strftime("%H:%M") in slots and slot != last_slot:
            try:
                with SessionLocal() as db:
                    service = PersonalAssetValuationService(db)
                    updated, stale = service.refresh()
                    snapshot = service.create_snapshot(now.replace(second=0, microsecond=0))
                    logger.info("snapshot id=%s total=%s updated=%s stale=%s", snapshot.id, snapshot.total_value, updated, stale)
                last_slot = slot
            except Exception:
                logger.exception("personal asset snapshot failed slot=%s", slot)
        sleep(20)


if __name__ == "__main__":
    run()
