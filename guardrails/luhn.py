"""Luhn validator for credit card numbers — kills false positives on order IDs like 20-digit refs."""
import re

def luhn_valid(s: str) -> bool:
    digits = re.sub(r"\D", "", s)
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    rev = digits[::-1]
    for i, ch in enumerate(rev):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

# Known test cards that must pass
_TEST_CARDS = ["4111111111111111", "5500000000000004", "378282246310005"]
assert all(luhn_valid(c) for c in _TEST_CARDS)
