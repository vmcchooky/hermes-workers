import unittest

from multiply import multiply


class TestMultiply(unittest.TestCase):
    def test_multiply_positive_numbers(self):
        self.assertEqual(multiply(2, 3), 6)

    def test_multiply_negative_numbers(self):
        self.assertEqual(multiply(-2, -3), 6)

    def test_multiply_mixed_numbers(self):
        self.assertEqual(multiply(-2, 3), -6)

    def test_multiply_by_zero(self):
        self.assertEqual(multiply(7, 0), 0)


if __name__ == "__main__":
    unittest.main()
