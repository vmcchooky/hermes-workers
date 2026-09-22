import unittest

from fizzbuzz import fizzbuzz


class TestFizzBuzz(unittest.TestCase):
    def test_multiple_of_three_returns_fizz(self):
        self.assertEqual(fizzbuzz(3), "Fizz")

    def test_multiple_of_five_returns_buzz(self):
        self.assertEqual(fizzbuzz(5), "Buzz")

    def test_multiple_of_both_returns_fizzbuzz(self):
        self.assertEqual(fizzbuzz(15), "FizzBuzz")

    def test_non_multiple_returns_number_as_string(self):
        self.assertEqual(fizzbuzz(7), "7")

    def test_zero_returns_fizzbuzz(self):
        self.assertEqual(fizzbuzz(0), "FizzBuzz")


if __name__ == "__main__":
    unittest.main()
