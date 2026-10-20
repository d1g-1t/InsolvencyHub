from collections.abc import Mapping
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from insolvency_hub.domain.errors import ValidationFailed

KOPECK = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: Decimal | int | str) -> Decimal:
    amount = Decimal(str(value)).quantize(KOPECK, rounding=ROUND_HALF_UP)
    if amount < 0:
        raise ValidationFailed("сумма не может быть отрицательной")
    return amount


def pro_rata[K](available: Decimal, demands: Mapping[K, Decimal]) -> dict[K, Decimal]:
    total = sum(demands.values(), ZERO)
    if total <= available:
        return dict(demands)
    if available <= 0 or total == 0:
        return dict.fromkeys(demands, ZERO)
    budget = int((available / KOPECK).to_integral_value(rounding=ROUND_DOWN))
    total_kopecks = int(total / KOPECK)
    shares: dict[K, int] = {}
    remainders: list[tuple[int, int, K]] = []
    for index, (key, value) in enumerate(demands.items()):
        numerator = int(value / KOPECK) * budget
        shares[key] = numerator // total_kopecks
        remainders.append((numerator % total_kopecks, -index, key))
    leftover = budget - sum(shares.values())
    for _, _, key in sorted(remainders, reverse=True)[:leftover]:
        shares[key] += 1
    return {key: Decimal(kopecks) * KOPECK for key, kopecks in shares.items()}
