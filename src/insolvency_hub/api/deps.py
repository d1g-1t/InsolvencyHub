from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from insolvency_hub.core.security import Permission, Principal, read_token

_bearer = HTTPBearer(auto_error=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


async def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "требуется токен", headers={"WWW-Authenticate": "Bearer"})
    try:
        return read_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "недействительный токен", headers={"WWW-Authenticate": "Bearer"}
        ) from exc


def require(permission: Permission) -> Callable[[Principal], Principal]:
    def check(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if not principal.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "недостаточно прав")
        return principal

    return check


def expected_version(if_match: Annotated[str | None, Header(alias="If-Match")] = None) -> int | None:
    if if_match is None:
        return None
    raw = if_match.strip().removeprefix("W/").strip('"')
    if not raw.isdigit():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "If-Match должен содержать номер версии дела")
    return int(raw)


Session = Annotated[AsyncSession, Depends(get_session)]
Reader = Annotated[Principal, Depends(require(Permission.READ))]
Writer = Annotated[Principal, Depends(require(Permission.WRITE))]
Requester = Annotated[Principal, Depends(require(Permission.REQUISITION))]
Admin = Annotated[Principal, Depends(require(Permission.ADMIN))]
Version = Annotated[int | None, Depends(expected_version)]
