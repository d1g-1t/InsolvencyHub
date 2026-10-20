import re

from insolvency_hub.domain.errors import ValidationFailed

_INN10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_A = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_B = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_CASE_NUMBER = re.compile(r"^А\d{2,3}-\d{1,7}/(\d{4})$")


def _control(digits: str, weights: tuple[int, ...]) -> int:
    return sum(int(d) * w for d, w in zip(digits, weights, strict=False)) % 11 % 10


def is_valid_inn(value: str) -> bool:
    if not value.isdigit():
        return False
    if len(value) == 10:
        return _control(value, _INN10) == int(value[9])
    if len(value) == 12:
        return _control(value, _INN12_A) == int(value[10]) and _control(value, _INN12_B) == int(value[11])
    return False


def is_valid_ogrn(value: str) -> bool:
    if not value.isdigit():
        return False
    if len(value) == 13:
        return int(value[:12]) % 11 % 10 == int(value[12])
    if len(value) == 15:
        return int(value[:14]) % 13 % 10 == int(value[14])
    return False


def is_valid_case_number(value: str) -> bool:
    return _CASE_NUMBER.match(value) is not None


def require_inn(value: str, *, length: int) -> str:
    if len(value) != length or not is_valid_inn(value):
        raise ValidationFailed(f"ИНН {value!r} не проходит проверку контрольных цифр")
    return value


def require_ogrn(value: str, *, length: int) -> str:
    if len(value) != length or not is_valid_ogrn(value):
        raise ValidationFailed(f"ОГРН {value!r} не проходит проверку контрольной цифры")
    return value


def require_case_number(value: str) -> str:
    if not is_valid_case_number(value):
        raise ValidationFailed("номер дела должен иметь вид А40-12345/2026")
    return value
