import os

import httpx

from app.config import required_secret
from app.contracts import JudgeRequest, JudgeResult
from app.plugin_sdk import ProviderUnavailable


class CustomProvider:
    def __init__(self):
        self.url = os.getenv("RUNNER_URL", "http://runner:8001")

    def capabilities(self):
        return {"implemented": True, "languages": ["c17", "cpp17"],
                "custom_input": True, "test_details": True, "partial_scoring": False}

    def health_check(self):
        try:
            return httpx.get(f"{self.url}/health", timeout=3).status_code == 200
        except httpx.HTTPError:
            return False

    def prepare_problem(self, problem_version_id):
        return problem_version_id

    def submit(self, request: JudgeRequest, idempotency_key: str):
        if idempotency_key != str(request.attempt_id):
            raise ValueError("Attempt key mismatch")
        try:
            response = httpx.post(
                f"{self.url}/judge", json=request.model_dump(mode="json"),
                headers={"X-Runner-Token": required_secret("RUNNER_TOKEN")}, timeout=140)
            response.raise_for_status()
            self._result = JudgeResult.model_validate(response.json())
            self._reference = idempotency_key
            return self._reference
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable("custom_runner_unavailable") from exc

    def get_result(self, reference):
        if reference != getattr(self, "_reference", None):
            raise ProviderUnavailable("unknown_custom_reference")
        return self._result
