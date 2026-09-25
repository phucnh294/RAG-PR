from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

ADMIN_ROLE = "admin"


@dataclass(frozen=True)
class UserRecord:
    """One row of the users table."""

    id: str
    username: str
    display_name: str | None
    role: str
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated caller of one request, resolved from the database.

    allowed_classifications is a snapshot of role_classification_access for the user's
    role, used for upload checks and the retrieval defence-in-depth filter. Row-level
    visibility itself is always enforced in SQL through the permission views.
    """

    id: str
    username: str
    role: str
    allowed_classifications: frozenset[str]

    @property
    def is_admin(self) -> bool:
        return self.role == ADMIN_ROLE

    def can_read(self, classification: str) -> bool:
        return classification in self.allowed_classifications
