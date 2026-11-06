from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import database_url


@lru_cache
def engine():
    url = database_url()
    options = {} if str(url).startswith("sqlite") else {"isolation_level": "READ COMMITTED"}
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, hide_parameters=True, **options)


def session():
    return Session(engine(), expire_on_commit=False)


def get_db():
    with session() as db:
        yield db
