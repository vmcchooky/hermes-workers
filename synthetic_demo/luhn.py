"""Utilities for validating numbers with the Luhn checksum algorithm."""


def is_valid_luhn(card_number: str) -> bool:
    """Return whether *card_number* passes the Luhn checksum.

    Spaces and hyphens are accepted as formatting characters. Any other
    non-ASCII digit makes the number invalid.
    """
    if not isinstance(card_number, str):
        return False

    number = card_number.replace(" ", "").replace("-", "")
    if not number or not all("0" <= character <= "9" for character in number):
        return False

    total = 0
    double_digit = len(number) % 2 == 0

    for character in number:
        digit = ord(character) - ord("0")
        if double_digit:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
        double_digit = not double_digit

    return total % 10 == 0
