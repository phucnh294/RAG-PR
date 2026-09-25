"""FastAPI dependencies that resolve the caller of a request.

Identity today is the X-User-Id header (the UI role picker sends the id of a seeded demo
user). The user and role are always loaded from the database, never taken from the
request, so swapping the header for a verified JWT/session later only changes how the id
is obtained in get_current_user.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from rag_backend.auth import repository, service
from rag_backend.auth.models import CurrentUser
from rag_backend.request_context import set_user_context

logger = logging.getLogger(__name__)

USER_ID_HEADER = "X-User-Id"


async def get_current_user(
    request: Request,
    x_user_id: Annotated[str | None, Header(alias=USER_ID_HEADER)] = None,
) -> CurrentUser:
    path = request.url.path
    if not x_user_id:
        logger.warning("AUTH rejected path=%s reason=missing %s header", path, USER_ID_HEADER)
        raise HTTPException(status_code=401, detail=f"Missing {USER_ID_HEADER} header")

    user = await repository.get_user(x_user_id)
    if user is None:
        logger.warning("AUTH rejected path=%s user_id=%s reason=unknown user", path, x_user_id)
        raise HTTPException(status_code=401, detail="Unknown user")
    if not user.is_active:
        logger.warning("AUTH rejected path=%s user=%s reason=inactive user", path, user.username)
        raise HTTPException(status_code=403, detail="User is inactive")

    current = await service.build_current_user(user)
    set_user_context(current.username, current.role)
    request.state.user = current
    logger.debug(
        "AUTH resolved user=%s role=%s allowed=%s",
        current.username,
        current.role,
        sorted(current.allowed_classifications),
    )
    return current


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def require_admin(user: CurrentUserDep) -> CurrentUser:
    if not user.is_admin:
        service.audit_denied(user, "admin_endpoint", "-", "admin role required")
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


AdminUserDep = Annotated[CurrentUser, Depends(require_admin)]
