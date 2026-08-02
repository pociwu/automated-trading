from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.api.routes import router
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.entities import Account


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        if db.scalar(select(Account).where(Account.name == "main")) is None:
            initial = get_settings().initial_capital
            db.add(Account(name="main", initial_capital=initial, cash=initial))
            db.commit()
    yield


app = FastAPI(title=get_settings().app_name, version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": get_settings().app_name, "docs": "/docs"}

