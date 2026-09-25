from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag_backend.auth import repository, seed
from rag_backend.config import Settings, settings


async def test_bootstrap_seeds_admin_demo_users_and_the_default_matrix() -> None:
    admin = await seed.bootstrap_authorization()

    assert admin.username == settings.admin_username
    assert admin.role == "admin"
    usernames = {user.username for user in await repository.list_users()}
    assert usernames == {"admin", "demo_user", "demo_staff", "demo_manager"}
    assert await repository.list_access() == {
        "user": ["public"],
        "staff": ["public", "internal"],
        "manager": ["public", "internal", "confidential"],
        "admin": ["public", "internal", "confidential", "restricted"],
    }


async def test_admin_username_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_username", "root")

    admin = await seed.bootstrap_authorization()

    assert admin.username == "root"


async def test_bootstrap_keeps_grants_revoked_in_the_database() -> None:
    await seed.bootstrap_authorization()
    await repository.revoke_access("staff", "internal")

    await seed.bootstrap_authorization()

    assert await repository.get_allowed_classifications("staff") == ["public"]


async def test_bootstrap_restores_a_demoted_admin() -> None:
    admin = await seed.bootstrap_authorization()
    await repository.set_user_role(admin.id, "user")

    restored = await seed.bootstrap_authorization()

    assert restored.id == admin.id
    assert restored.role == "admin"


async def test_demo_users_are_not_seeded_outside_dev_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_dev_mode", False)

    await seed.bootstrap_authorization()

    assert [user.username for user in await repository.list_users()] == ["admin"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"auth_default_classification": "top-secret"},
        {"auth_role_access": {"ghost": ["public"]}},
        {"auth_role_access": {"user": ["top-secret"]}},
        {"auth_roles": ["user", "staff"]},
    ],
)
def test_settings_reject_inconsistent_authorization_config(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(**overrides)  # type: ignore[arg-type]
