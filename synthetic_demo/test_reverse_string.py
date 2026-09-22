import unittest

from reverse_string import reverse_string


class TestReverseString(unittest.TestCase):
    def test_reverses_regular_string(self):
        self.assertEqual(reverse_string("hello"), "olleh")

    def test_reverses_empty_string(self):
        self.assertEqual(reverse_string(""), "")

    def test_reverses_string_with_spaces_and_punctuation(self):
        self.assertEqual(reverse_string("a b!"), "!b a")


if __name__ == "__main__":
    unittest.main()
