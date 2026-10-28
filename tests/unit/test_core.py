from datetime import timedelta

import pyseto
import pytest

from insolvency_hub.core import security
from insolvency_hub.core.config import DEV_KEY, Settings
from insolvency_hub.core.security import (
    ROLE_PERMISSIONS,
    Permission,
    Principal,
    Role,
    hash_password,
    issue_token,
    read_token,
    verify_password,
)


def test_password_hashing() -> None:
    hashed = hash_password("секрет-123")
    assert verify_password("секрет-123", hashed)
    assert not verify_password("другой", hashed)


def test_role_permissions() -> None:
    assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset(Permission)
    assert Principal("u", "o", Role.CREDITOR).can(Permission.REQUISITION)
    assert not Principal("u", "o", Role.CREDITOR).can(Permission.WRITE)
    assert not Principal("u", "o", Role.AUDITOR).can(Permission.REQUISITION)


def test_token_round_trip() -> None:
    principal = Principal("user-1", "org-1", Role.MANAGER)
    assert read_token(issue_token(principal)) == principal


def test_tampered_token_rejected() -> None:
    token = issue_token(Principal("u", "o", Role.ADMIN))
    with pytest.raises(pyseto.DecryptError):
        read_token(token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB"))


def test_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    token = issue_token(Principal("u", "o", Role.ADMIN))
    later = security.now() + timedelta(hours=2)
    monkeypatch.setattr(security, "now", lambda: later)
    with pytest.raises((ValueError, pyseto.VerifyError)):
        read_token(token)


def test_settings_key_validation() -> None:
    assert Settings(paseto_key_hex="ab" * 32).paseto_key_hex.get_secret_value() == "ab" * 32
    with pytest.raises(ValueError, match="32 bytes"):
        Settings(paseto_key_hex="abc")
    with pytest.raises(ValueError, match="prod"):
        Settings(env="prod", paseto_key_hex=DEV_KEY)
