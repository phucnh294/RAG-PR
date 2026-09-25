"""Authorization business rules: who may assign roles, change the access matrix, upload
into a classification, or delete a document.

Every decision is logged as an audit line ("AUTH <action> ...") — INFO when allowed,
WARNING when denied — so permission changes and denials can be traced from the console.
"""

from __future__ import annotations

import logging

from rag_backend.auth import repository
from rag_backend.auth.models import CurrentUser, UserRecord
from rag_backend.config import settings
from rag_backend.exceptions import (
    InvalidClassificationError,
    InvalidRoleError,
    PermissionDeniedError,
    UnknownUserError,
    UserAlreadyExistsError,
)
from rag_backend.storage.records import DocumentRecord

logger = logging.getLogger(__name__)


def audit_denied(actor: CurrentUser, action: str, target: str, reason: str) -> None:
    logger.warning(
        "AUTH denied action=%s actor=%s role=%s target=%s reason=%s",
        action,
        actor.username,
        actor.role,
        target,
        reason,
    )


def _audit_allowed(actor: CurrentUser, action: str, target: str) -> None:
    logger.info(
        "AUTH allowed action=%s actor=%s role=%s target=%s",
        action,
        actor.username,
        actor.role,
        target,
    )


def _require_admin(actor: CurrentUser, action: str, target: str) -> None:
    if not actor.is_admin:
        audit_denied(actor, action, target, "admin role required")
        raise PermissionDeniedError(f"{action} requires the admin role")


async def _require_known_role(role: str) -> None:
    if role not in await repository.list_roles():
        raise InvalidRoleError(f"Unknown role: {role}")


async def _require_known_classification(classification: str) -> None:
    if classification not in await repository.list_classifications():
        raise InvalidClassificationError(f"Unknown classification: {classification}")


async def build_current_user(user: UserRecord) -> CurrentUser:
    allowed = await repository.get_allowed_classifications(user.role)
    return CurrentUser(
        id=user.id,
        username=user.username,
        role=user.role,
        allowed_classifications=frozenset(allowed),
    )


async def create_user(
    actor: CurrentUser, username: str, display_name: str | None, role: str | None
) -> UserRecord:
    target_role = role or settings.auth_default_user_role
    _require_admin(actor, "create_user", username)
    await _require_known_role(target_role)
    if await repository.get_user_by_username(username) is not None:
        raise UserAlreadyExistsError(f"User {username!r} already exists")
    created = await repository.create_user(username, display_name, target_role)
    _audit_allowed(actor, "create_user", f"{username} role={target_role}")
    return created


async def assign_user_role(actor: CurrentUser, user_id: str, role: str) -> UserRecord:
    """Change a user's role. Admin only; an admin may not demote themselves (lock-out guard)."""
    _require_admin(actor, "assign_role", f"{user_id} -> {role}")
    await _require_known_role(role)
    if user_id == actor.id and role != actor.role:
        audit_denied(actor, "assign_role", f"{user_id} -> {role}", "cannot change own role")
        raise PermissionDeniedError("Admins cannot change their own role")
    updated = await repository.set_user_role(user_id, role)
    if updated is None:
        raise UnknownUserError(f"User {user_id} not found")
    _audit_allowed(actor, "assign_role", f"{updated.username} -> {role}")
    return updated


async def set_user_active(actor: CurrentUser, user_id: str, is_active: bool) -> UserRecord:
    _require_admin(actor, "set_user_active", f"{user_id} -> {is_active}")
    if user_id == actor.id and not is_active:
        audit_denied(actor, "set_user_active", user_id, "cannot deactivate self")
        raise PermissionDeniedError("Admins cannot deactivate themselves")
    updated = await repository.set_user_active(user_id, is_active)
    if updated is None:
        raise UnknownUserError(f"User {user_id} not found")
    _audit_allowed(actor, "set_user_active", f"{updated.username} -> {is_active}")
    return updated


async def grant_classification(actor: CurrentUser, role: str, classification: str) -> bool:
    target = f"{role} -> {classification}"
    _require_admin(actor, "grant_access", target)
    await _require_known_role(role)
    await _require_known_classification(classification)
    granted = await repository.grant_access(role, classification, actor.id)
    _audit_allowed(actor, "grant_access", f"{target} (new={granted})")
    return granted


async def revoke_classification(actor: CurrentUser, role: str, classification: str) -> bool:
    target = f"{role} -> {classification}"
    _require_admin(actor, "revoke_access", target)
    await _require_known_role(role)
    await _require_known_classification(classification)
    revoked = await repository.revoke_access(role, classification)
    _audit_allowed(actor, "revoke_access", f"{target} (existed={revoked})")
    return revoked


async def resolve_upload_classification(
    user: CurrentUser, requested: str | None, frontmatter_value: str | None = None
) -> str:
    """Pick the classification for a new upload: explicit request, then the document's own
    frontmatter, then the configured default. Nobody may upload above their own clearance,
    otherwise they could create a document they themselves cannot see or delete.

    Only an explicit choice is ever rejected: when the configured default is above the
    user's clearance (e.g. a plain "user" and default "internal"), the default is capped
    at the highest classification the user can read instead.
    """
    explicit = (requested or "").strip() or (frontmatter_value or "").strip()
    classification = explicit or default_classification_for(user)
    await _require_known_classification(classification)
    if not user.can_read(classification):
        audit_denied(user, "upload", classification, "classification above user clearance")
        raise PermissionDeniedError(
            f"Role {user.role!r} cannot upload documents classified {classification!r}"
        )
    return classification


def default_classification_for(user: CurrentUser) -> str:
    """The classification an upload gets when the user picks none (shown in the UI)."""
    default = settings.auth_default_classification
    if user.can_read(default):
        return default
    ordered = settings.auth_classifications
    ceiling = ordered.index(default)
    readable = [name for name in ordered[:ceiling] if user.can_read(name)]
    if readable:
        logger.info(
            "Default classification %s is above role %s; using %s",
            default,
            user.role,
            readable[-1],
        )
        return readable[-1]
    return default


def can_delete(user: CurrentUser, document: DocumentRecord) -> bool:
    """Creator or admin — and only for documents the user can read at all."""
    if not user.can_read(document.classification):
        return False
    return user.is_admin or document.created_by == user.id
