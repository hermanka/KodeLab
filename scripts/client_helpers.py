"""Integration helpers. Credentials enter via stdin, never command arguments/logs."""
import json
import secrets
import sys
import time
from uuid import uuid4

import httpx

BASE = "http://localhost:8000"


def login(username, password):
    client = httpx.Client(base_url=BASE, timeout=15)
    response = client.post("/auth/login", json={"username": username, "password": password})
    if response.status_code != 200:
        raise RuntimeError("Integration login failed; check bootstrap credentials and rate limits")
    client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
    return client


def admin_client():
    data = json.load(sys.stdin)
    return login(data["username"], data["password"])


def make_user(admin, role="student"):
    username = role + "_" + uuid4().hex[:12]
    password = secrets.token_urlsafe(32)
    response = admin.post("/admin/users", json={"username": username, "password": password, "role": role})
    assert response.status_code == 201, "Unable to create integration account"
    return login(username, password), response.json()


def wait_for(client, path, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        response = client.get(path)
        assert response.status_code == 200, f"Unable to read integration result ({response.status_code})"
        row = response.json()
        assert row["state"] != "system_error", "Integration judging infrastructure failed"
        if row["state"] == "completed":
            return row
        time.sleep(0.5)
    raise AssertionError("Integration result timed out")
