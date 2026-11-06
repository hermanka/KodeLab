import os
from functools import lru_cache

from sqlalchemy import URL


@lru_cache
def database_url():
    # SQLITE_URL exists only for isolated unit tests, not the Compose deployment.
    if os.getenv("SQLITE_URL"):
        return os.environ["SQLITE_URL"]
    return URL.create(
        "mysql+pymysql", username=os.getenv("DB_USER", "judgement"),
        password=os.environ["DB_PASSWORD"], host=os.getenv("DB_HOST", "db"),
        database=os.getenv("DB_NAME", "judgement"), query={"charset": "utf8mb4"},
    )


def required_secret(name):
    value = os.environ.get(name, "")
    if len(value) < 24 or value.startswith("replace-"):
        raise RuntimeError(f"{name} must be a random secret with at least 24 characters")
    return value
