from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Language = Literal["c17", "cpp17"]
Verdict = Literal[
    "ACCEPTED", "WRONG_ANSWER", "COMPILATION_ERROR", "RUNTIME_ERROR",
    "TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED", "EXECUTED",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Limits(StrictModel):
    compile_seconds: int = Field(default=10, ge=1, le=15)
    time_seconds: int = Field(default=2, ge=1, le=5)
    memory_mb: int = Field(default=128, ge=64, le=256)
    output_bytes: int = Field(default=65536, ge=1024, le=65536)


class SubmitRequest(StrictModel):
    problem_version_id: str = Field(default="sum-v1", max_length=80)
    language: Language
    source: str = Field(min_length=1, max_length=32768)
    provider: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{0,29}$")
    enrollment_id: UUID | None = None
    path_step_id: UUID | None = None

    @model_validator(mode="after")
    def path_context(self):
        if bool(self.enrollment_id) != bool(self.path_step_id):
            raise ValueError("Enrollment and path step must be supplied together")
        return self

    @field_validator("source")
    @classmethod
    def source_size(cls, value):
        if len(value.encode()) > 32768 or "\x00" in value:
            raise ValueError("Source must be <=32768 UTF-8 bytes and contain no NUL")
        return value


class ReplayInput(StrictModel):
    input: str = Field(default="", max_length=32768)

    @field_validator("input")
    @classmethod
    def input_size(cls, value):
        if len(value.encode()) > 32768:
            raise ValueError("Input must be <=32768 UTF-8 bytes")
        return value


class RunRequest(SubmitRequest):
    input: str = Field(default="", max_length=32768)

    @field_validator("input")
    @classmethod
    def input_size(cls, value):
        if len(value.encode()) > 32768:
            raise ValueError("Input must be <=32768 UTF-8 bytes")
        return value


class Case(StrictModel):
    id: str = Field(max_length=80)
    input: str = Field(max_length=32768)
    expected: str | None = Field(default=None, max_length=32768)
    public: bool = False


class JudgeRequest(StrictModel):
    attempt_id: UUID
    language: Language
    source: str = Field(min_length=1, max_length=32768)
    mode: Literal["judge", "run"]
    checker: Literal["tokens-v1"] = "tokens-v1"
    limits: Limits
    cases: list[Case] = Field(min_length=1, max_length=10)


class CaseResult(StrictModel):
    id: str
    verdict: Verdict
    stdout: str = ""
    stderr: str = ""
    time_ms: int | None = None


class JudgeResult(StrictModel):
    verdict: Verdict
    compile_log: str = ""
    cases: list[CaseResult] = Field(default_factory=list)
    environment: str = ""


class JudgeProvider(Protocol):
    def capabilities(self) -> dict: ...
    def health_check(self) -> bool: ...
    def prepare_problem(self, problem_version_id: str) -> str: ...
    def submit(self, request: JudgeRequest, idempotency_key: str) -> str: ...
    def get_result(self, reference: str) -> JudgeResult: ...
