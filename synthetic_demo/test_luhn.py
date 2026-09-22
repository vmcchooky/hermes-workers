import unittest

from luhn import is_valid_luhn


class TestIsValidLuhn(unittest.TestCase):
    def test_valid_numbers(self):
        valid_numbers = (
            "4532015112830366",
            "5555555555554444",
            "79927398713",
        )

        for number in valid_numbers:
            with self.subTest(number=number):
                self.assertTrue(is_valid_luhn(number))

    def test_invalid_numbers(self):
        invalid_numbers = (
            "4532015112830367",
            "5555555555554445",
            "79927398714",
            "1234567890",
        )

        for number in invalid_numbers:
            with self.subTest(number=number):
                self.assertFalse(is_valid_luhn(number))

    def test_formatted_number(self):
        self.assertTrue(is_valid_luhn("4532 0151 1283 0366"))
        self.assertTrue(is_valid_luhn("4532-0151-1283-0366"))

    def test_empty_or_non_numeric_input(self):
        self.assertFalse(is_valid_luhn(""))
        self.assertFalse(is_valid_luhn("4532x0151"))
        self.assertFalse(is_valid_luhn(None))


if __name__ == "__main__":
    unittest.main()
