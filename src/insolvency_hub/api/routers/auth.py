from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from insolvency_hub.api.deps import Session, get_principal
from insolvency_hub.api.schemas import LoginIn, MeOut, TokenOut
from insolvency_hub.core.security import Principal, Role, issue_token, verify_password
from insolvency_hub.infrastructure.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginIn, session: Session) -> TokenOut:
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "неверный email или пароль")
    return TokenOut(access_token=issue_token(Principal(user.id, user.organization_id, Role(user.role))))


@router.get("/me")
async def me(principal: Annotated[Principal, Depends(get_principal)]) -> MeOut:
    return MeOut(user_id=principal.user_id, organization_id=principal.organization_id, role=principal.role.value)
