import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

import bcrypt
import pyseto

from insolvency_hub.core.clock import now
from insolvency_hub.core.config import get_settings


class Role(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    CREDITOR = "creditor"
    AUDITOR = "auditor"


class Permission(StrEnum):
    READ = "read"
    WRITE = "write"
    REQUISITION = "requisition"
    ADMIN = "admin"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.MANAGER: frozenset({Permission.READ, Permission.WRITE, Permission.REQUISITION}),
    Role.CREDITOR: frozenset({Permission.READ, Permission.REQUISITION}),
    Role.AUDITOR: frozenset({Permission.READ}),
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    organization_id: str
    role: Role

    def can(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[self.role]


def _key() -> pyseto.KeyInterface:
    raw = bytes.fromhex(get_settings().paseto_key_hex.get_secret_value())
    if len(raw) != 32:
        raise ValueError("IH_PASETO_KEY_HEX must encode 32 bytes")
    return pyseto.Key.new(version=4, purpose="local", key=raw)


def issue_token(principal: Principal) -> str:
    issued = now()
    claims = {
        "sub": principal.user_id,
        "org": principal.organization_id,
        "role": principal.role.value,
        "iat": issued.isoformat(),
        "exp": (issued + timedelta(minutes=get_settings().token_ttl_minutes)).isoformat(),
    }
    return pyseto.encode(_key(), json.dumps(claims).encode(), implicit_assertion=b"insolvency-hub").decode()


def read_token(token: str) -> Principal:
    decoded = pyseto.decode(_key(), token, deserializer=json, implicit_assertion=b"insolvency-hub")
    payload = decoded.payload
    if not isinstance(payload, dict):
        raise ValueError("malformed token")
    if datetime.fromisoformat(payload["exp"]) <= now():
        raise ValueError("token expired")
    return Principal(payload["sub"], payload["org"], Role(payload["role"]))
