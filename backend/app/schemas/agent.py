"""Pydantic schemas for advanced AI features."""
import uuid
from typing import Any, Optional

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Database connections
# ---------------------------------------------------------------------------

class DbConnectionCreate(BaseModel):
    name: str
    db_type: str  # postgresql | mysql | mssql | sqlite
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    full_url: Optional[str] = None  # full connection string (alternative to fields above)

    @field_validator("db_type")
    @classmethod
    def validate_db_type(cls, v: str) -> str:
        allowed = {"postgresql", "mysql", "mssql", "sqlite"}
        if v.lower() not in allowed:
            raise ValueError(f"db_type must be one of {allowed}")
        return v.lower()


class DbConnectionResponse(BaseModel):
    id: str
    name: str
    db_type: str
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Image rules
# ---------------------------------------------------------------------------

class RuleItem(BaseModel):
    field: str
    operator: str  # lt | gt | eq | ne | contains | not_contains | present | absent
    value: Optional[Any] = None
    type: str = "text"  # numeric | text | presence
    label: Optional[str] = None


class ImageRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    rules: list[RuleItem]


class ImageRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rules: Optional[list[RuleItem]] = None


class ImageRuleResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    rules: list[dict]
    created_at: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Validation results
# ---------------------------------------------------------------------------

class ValidationRuleResult(BaseModel):
    rule: str
    field: str
    extracted: Optional[Any] = None
    expected: Optional[Any] = None
    operator: str
    passed: bool


class ImageValidationResponse(BaseModel):
    rule_name: str
    extracted: dict[str, Any]
    results: list[ValidationRuleResult]
    passed: bool
    violation_count: int
    summary: str


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AgentRunRequest(BaseModel):
    task: str
    thread_id: Optional[str] = None


class AgentRunResponse(BaseModel):
    answer: str
    steps: list[str]


# ---------------------------------------------------------------------------
# Thread context (stored as JSON in chat_thread.context)
# ---------------------------------------------------------------------------

class ThreadContext(BaseModel):
    db_connection_id: Optional[str] = None
    agent_mode: bool = False
