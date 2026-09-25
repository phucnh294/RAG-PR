from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str | None
    role: str
    is_active: bool
    created_at: datetime


class MeOut(BaseModel):
    id: str
    username: str
    role: str
    allowed_classifications: list[str]
    is_admin: bool


class ClassificationsOut(BaseModel):
    """What the upload form needs: every classification the caller may upload into, and
    the one an upload gets when none is chosen."""

    allowed: list[str]
    default: str
    all: list[str]


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    display_name: str | None = None
    role: str | None = None


class AssignRoleRequest(BaseModel):
    role: str


class SetActiveRequest(BaseModel):
    is_active: bool


class AccessChangeRequest(BaseModel):
    role: str
    classification: str
    granted: bool


class AccessMatrixOut(BaseModel):
    roles: list[str]
    classifications: list[str]
    access: dict[str, list[str]]
