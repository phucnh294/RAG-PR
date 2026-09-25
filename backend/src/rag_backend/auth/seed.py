"""Startup seeding of the authorization tables from config/env.

Roles and classifications are insert-if-missing. Each AUTH_ROLE_ACCESS grant is applied
exactly once (tracked in authz_seeded_grants): a grant added to config later is applied on
the next restart, while a grant an admin revoked in the database stays revoked. The admin
account is the exception: ADMIN_USERNAME is always (re)forced to the admin role and
active, so a lost admin can be recovered by restarting the backend.
"""

from __future__ import annotations

import logging

from rag_backend.auth import repository
from rag_backend.auth.models import ADMIN_ROLE, UserRecord
from rag_backend.config import settings

logger = logging.getLogger(__name__)


def demo_username(role: str) -> str:
    return f"demo_{role}"


async def sync_roles_and_classifications() -> None:
    new_roles = [
        name
        for rank, name in enumerate(settings.auth_roles)
        if await repository.ensure_role(name, rank)
    ]
    new_classifications = [
        name
        for level, name in enumerate(settings.auth_classifications)
        if await repository.ensure_classification(name, level)
    ]
    new_grants = [
        f"{role}->{classification}"
        for role, classifications in settings.auth_role_access.items()
        for classification in classifications
        if await repository.mark_grant_seeded(role, classification)
        and await repository.grant_access(role, classification, granted_by=None)
    ]
    logger.info(
        "Authorization config synced: new roles=%s, new classifications=%s, new grants=%s",
        new_roles,
        new_classifications,
        new_grants,
    )


async def seed_admin_from_env() -> UserRecord:
    admin = await repository.upsert_user(
        settings.admin_username, settings.admin_display_name, ADMIN_ROLE
    )
    logger.info("Admin user seeded from env: username=%s id=%s", admin.username, admin.id)
    return admin


async def seed_demo_users() -> list[UserRecord]:
    """One demo user per non-admin role, for the UI role picker. Dev mode only."""
    if not settings.auth_dev_mode:
        logger.info("AUTH_DEV_MODE is off: demo users not seeded")
        return []
    seeded = [
        await repository.upsert_user(demo_username(role), f"Demo {role}", role)
        for role in settings.auth_roles
        if role != ADMIN_ROLE
    ]
    logger.info("Demo users seeded: %s", [f"{user.username}({user.role})" for user in seeded])
    return seeded


async def bootstrap_authorization() -> UserRecord:
    """Run every seeding step in dependency order; returns the admin user."""
    await sync_roles_and_classifications()
    admin = await seed_admin_from_env()
    await seed_demo_users()
    return admin
