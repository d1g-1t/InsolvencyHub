import pytest
from hypothesis import given
from hypothesis import strategies as st

from insolvency_hub.domain.errors import ValidationFailed
from insolvency_hub.domain.identifiers import (
    _INN10,
    _INN12_A,
    _INN12_B,
    _control,
    is_valid_case_number,
    is_valid_inn,
    is_valid_ogrn,
    require_case_number,
    require_inn,
    require_ogrn,
)


def make_inn10(body: str) -> str:
    return body + str(_control(body, _INN10))


def make_inn12(body: str) -> str:
    first = body + str(_control(body, _INN12_A))
    return first + str(_control(first, _INN12_B))


def make_ogrn(body: str) -> str:
    modulus = 11 if len(body) == 12 else 13
    return body + str(int(body) % modulus % 10)


@pytest.mark.parametrize("value", ["0000000018", "000000000184", "9999000013", "999900001291"])
def test_valid_inn(value: str) -> None:
    assert is_valid_inn(value)


@pytest.mark.parametrize("value", ["0000000019", "000000000185", "12345", "abcdefghij", ""])
def test_invalid_inn(value: str) -> None:
    assert not is_valid_inn(value)


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("1000000000010", True),
        ("1029999000019", True),
        ("1000000000011", False),
        ("304999900000012", True),
        ("304999900000013", False),
        ("12", False),
        ("x" * 13, False),
    ],
)
def test_ogrn(value: str, ok: bool) -> None:
    assert is_valid_ogrn(value) is ok


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("А40-12345/2026", True),
        ("А00-1/2026", True),
        ("A40-12345/2026", False),
        ("А40-12345/26", False),
    ],
)
def test_case_number(value: str, ok: bool) -> None:
    assert is_valid_case_number(value) is ok


def test_require_helpers() -> None:
    assert require_inn("0000000018", length=10) == "0000000018"
    with pytest.raises(ValidationFailed):
        require_inn("0000000018", length=12)
    with pytest.raises(ValidationFailed):
        require_ogrn("1000000000011", length=13)
    with pytest.raises(ValidationFailed):
        require_case_number("40-1/2026")


@given(st.text(alphabet="0123456789", min_size=9, max_size=9))
def test_generated_inn10_valid_and_detects_typo(body: str) -> None:
    inn = make_inn10(body)
    assert is_valid_inn(inn)
    broken = inn[:-1] + str((int(inn[-1]) + 1) % 10)
    assert not is_valid_inn(broken)


@given(st.text(alphabet="0123456789", min_size=10, max_size=10))
def test_generated_inn12_valid(body: str) -> None:
    assert is_valid_inn(make_inn12(body))


@given(
    st.one_of(
        st.text(alphabet="0123456789", min_size=12, max_size=12),
        st.text(alphabet="0123456789", min_size=14, max_size=14),
    )
)
def test_generated_ogrn_valid(body: str) -> None:
    ogrn = make_ogrn(body)
    assert is_valid_ogrn(ogrn)
    assert not is_valid_ogrn(ogrn[:-1] + str((int(ogrn[-1]) + 1) % 10))
