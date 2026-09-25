from __future__ import annotations

from fastapi import APIRouter, HTTPException

from rag_backend.auth import repository, service
from rag_backend.auth.dependencies import AdminUserDep, CurrentUserDep
from rag_backend.auth.models import UserRecord
from rag_backend.config import settings
from rag_backend.schemas.auth import (
    AccessChangeRequest,
    AccessMatrixOut,
    AssignRoleRequest,
    ClassificationsOut,
    CreateUserRequest,
    MeOut,
    SetActiveRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_user_out(user: UserRecord) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/demo-users", response_model=list[UserOut])
async def list_demo_users() -> list[UserOut]:
    """Unauthenticated user list for the UI role picker. Only exists in dev mode."""
    if not settings.auth_dev_mode:
        raise HTTPException(status_code=404, detail="Not found")
    return [_to_user_out(user) for user in await repository.list_users() if user.is_active]


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUserDep) -> MeOut:
    return MeOut(
        id=user.id,
        username=user.username,
        role=user.role,
        allowed_classifications=[
            name for name in await repository.list_classifications() if user.can_read(name)
        ],
        is_admin=user.is_admin,
    )


@router.get("/classifications", response_model=ClassificationsOut)
async def classifications(user: CurrentUserDep) -> ClassificationsOut:
    every = await repository.list_classifications()
    return ClassificationsOut(
        allowed=[name for name in every if user.can_read(name)],
        default=service.default_classification_for(user),
        all=every,
    )


@router.get("/users", response_model=list[UserOut])
async def list_users(_: AdminUserDep) -> list[UserOut]:
    return [_to_user_out(user) for user in await repository.list_users()]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(request: CreateUserRequest, admin: AdminUserDep) -> UserOut:
    created = await service.create_user(admin, request.username, request.display_name, request.role)
    return _to_user_out(created)


@router.put("/users/{user_id}/role", response_model=UserOut)
async def assign_role(user_id: str, request: AssignRoleRequest, admin: AdminUserDep) -> UserOut:
    return _to_user_out(await service.assign_user_role(admin, user_id, request.role))


@router.put("/users/{user_id}/active", response_model=UserOut)
async def set_active(user_id: str, request: SetActiveRequest, admin: AdminUserDep) -> UserOut:
    return _to_user_out(await service.set_user_active(admin, user_id, request.is_active))


@router.get("/access", response_model=AccessMatrixOut)
async def get_access(_: AdminUserDep) -> AccessMatrixOut:
    return AccessMatrixOut(
        roles=await repository.list_roles(),
        classifications=await repository.list_classifications(),
        access=await repository.list_access(),
    )


@router.put("/access", response_model=AccessMatrixOut)
async def change_access(request: AccessChangeRequest, admin: AdminUserDep) -> AccessMatrixOut:
    if request.granted:
        await service.grant_classification(admin, request.role, request.classification)
    else:
        await service.revoke_classification(admin, request.role, request.classification)
    return await get_access(admin)
