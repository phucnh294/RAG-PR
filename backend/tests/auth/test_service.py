from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rag_backend.auth import service
from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.exceptions import (
    InvalidClassificationError,
    InvalidRoleError,
    PermissionDeniedError,
)
from rag_backend.storage.records import DocumentRecord


def _document(classification: str, created_by: str | None) -> DocumentRecord:
    return DocumentRecord(
        id="doc-1",
        filename="f.md",
        content_hash="h",
        mime_type="text/markdown",
        size_bytes=1,
        status="ready",
        created_at=datetime.now(UTC),
        classification=classification,
        created_by=created_by,
    )


async def test_assign_user_role_is_admin_only(auth_users: dict[str, CurrentUser]) -> None:
    with pytest.raises(PermissionDeniedError):
        await service.assign_user_role(auth_users["manager"], auth_users["user"].id, "staff")


async def test_assign_user_role_changes_the_role(auth_users: dict[str, CurrentUser]) -> None:
    updated = await service.assign_user_role(auth_users["admin"], auth_users["user"].id, "staff")

    assert updated.role == "staff"


async def test_assign_user_role_rejects_unknown_role(auth_users: dict[str, CurrentUser]) -> None:
    with pytest.raises(InvalidRoleError):
        await service.assign_user_role(auth_users["admin"], auth_users["user"].id, "superuser")


async def test_admin_cannot_demote_themselves(auth_users: dict[str, CurrentUser]) -> None:
    admin = auth_users["admin"]
    with pytest.raises(PermissionDeniedError):
        await service.assign_user_role(admin, admin.id, "user")


async def test_resolve_upload_classification_uses_explicit_then_frontmatter_then_default(
    auth_users: dict[str, CurrentUser],
) -> None:
    manager = auth_users["manager"]

    assert await service.resolve_upload_classification(manager, "confidential", "public") == (
        "confidential"
    )
    assert await service.resolve_upload_classification(manager, None, "public") == "public"
    assert await service.resolve_upload_classification(manager, None, None) == (
        settings.auth_default_classification
    )


async def test_resolve_upload_classification_denies_above_clearance(
    auth_users: dict[str, CurrentUser],
) -> None:
    with pytest.raises(PermissionDeniedError):
        await service.resolve_upload_classification(auth_users["staff"], "confidential")


async def test_resolve_upload_classification_rejects_unknown_classification(
    auth_users: dict[str, CurrentUser],
) -> None:
    with pytest.raises(InvalidClassificationError):
        await service.resolve_upload_classification(auth_users["admin"], "top-secret")


async def test_default_classification_is_capped_at_user_clearance(
    auth_users: dict[str, CurrentUser],
) -> None:
    # Default is "internal", which a plain user cannot read: they get "public" instead
    # of an upload they could never see again.
    assert await service.resolve_upload_classification(auth_users["user"], None) == "public"


def test_can_delete_allows_creator_and_admin_only(auth_users: dict[str, CurrentUser]) -> None:
    staff, manager, admin = auth_users["staff"], auth_users["manager"], auth_users["admin"]
    staff_doc = _document("internal", created_by=staff.id)

    assert service.can_delete(staff, staff_doc)
    assert service.can_delete(admin, staff_doc)
    assert not service.can_delete(manager, staff_doc)


def test_can_delete_requires_read_access(auth_users: dict[str, CurrentUser]) -> None:
    user = auth_users["user"]
    # Even the creator loses delete rights once their role can no longer read the doc.
    assert not service.can_delete(user, _document("internal", created_by=user.id))


async def test_grant_and_revoke_change_what_a_role_can_read(
    auth_users: dict[str, CurrentUser],
) -> None:
    admin = auth_users["admin"]

    assert await service.grant_classification(admin, "user", "internal") is True
    user_record = await service.repository.get_user(auth_users["user"].id)
    assert user_record is not None
    assert (await service.build_current_user(user_record)).can_read("internal")

    assert await service.revoke_classification(admin, "user", "internal") is True
    assert not (await service.build_current_user(user_record)).can_read("internal")


async def test_changing_the_access_matrix_is_admin_only(
    auth_users: dict[str, CurrentUser],
) -> None:
    with pytest.raises(PermissionDeniedError):
        await service.grant_classification(auth_users["manager"], "user", "restricted")
