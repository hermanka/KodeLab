"""Create the first local administrator without printing or replacing credentials."""
import os

from sqlalchemy import select

from app.auth import CreateUser, create_user
from app.db import session
from app.models import User


def main():
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not password:
        print("No bootstrap password configured; no account created.")
        return
    if password.startswith("replace-"):
        raise RuntimeError("Replace the bootstrap password placeholder with a random secret")
    try:
        data = CreateUser(username=username, password=password, role="admin")
    except ValueError:
        # ValidationError normally includes its input; never echo bootstrap secrets.
        raise RuntimeError("Invalid bootstrap account settings; check username and password policy") from None
    with session() as db:
        existing = db.scalar(select(User).where(User.username == data.username))
        if existing:
            if existing.role != "admin":
                raise RuntimeError("Bootstrap username belongs to a non-administrator")
            print("Existing administrator kept unchanged.")
            return
        # Once an administrator exists, bootstrap cannot create additional administrators.
        if db.scalar(select(User.id).where(User.role == "admin").limit(1)):
            print("An administrator already exists; use account management for additional users.")
            return
        create_user(db, data)
        print("Local administrator created. Credentials are not printed.")


if __name__ == "__main__":
    main()
