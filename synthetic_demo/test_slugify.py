import unittest

from slugify import slugify


class TestSlugify(unittest.TestCase):
    def test_lowercases_text(self):
        self.assertEqual(slugify("Hello WORLD"), "hello-world")

    def test_replaces_whitespace_with_hyphens(self):
        self.assertEqual(
            slugify("multiple   spaces\tand\nlines"),
            "multiple-spaces-and-lines",
        )

    def test_empty_text(self):
        self.assertEqual(slugify(""), "")


if __name__ == "__main__":
    unittest.main()
