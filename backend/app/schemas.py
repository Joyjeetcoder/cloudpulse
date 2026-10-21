from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


Category = Literal["Test failure", "Dependency error", "Syntax/build error",
                   "Configuration error", "Infrastructure error", "Other", "Unknown"]


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category
    root_cause: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(max_length=6)
    suggested_fix: str = Field(min_length=1, max_length=2000)
    uncertainty: Literal["low", "medium", "high"]
    insufficient_evidence: bool


class ImportRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    run_id: int = Field(gt=0)


class ServiceError(Exception):
    """Only safe, deliberately written messages may be exposed to the UI."""
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable
