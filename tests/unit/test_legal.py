import re
from pathlib import Path

from insolvency_hub.domain.legal import CHECKED_ON, NORMS, cite

SRC = Path(__file__).resolve().parents[2] / "src"
CODE = re.compile(r"\"((?:127-FZ|GK|APK|TK|PP):[0-9.a-z]+)\"")


def test_every_cited_norm_is_in_catalog() -> None:
    used: set[str] = set()
    for path in SRC.rglob("*.py"):
        if path.name != "legal.py":
            used |= set(CODE.findall(path.read_text(encoding="utf-8")))
    assert used
    assert used <= set(NORMS), sorted(used - set(NORMS))


def test_norms_have_quotes_and_editions() -> None:
    for code, norm in NORMS.items():
        assert norm.code == code
        assert len(norm.quote) > 40
        assert "ред. от" in norm.act or "Постановление" in norm.act


def test_cite_and_check_date() -> None:
    assert cite("127-FZ:71.1") == ("127-FZ:71.1",)
    assert CHECKED_ON == "2026-10-16"


def test_cite_rejects_unknown() -> None:
    import pytest

    with pytest.raises(KeyError):
        cite("127-FZ:999")
