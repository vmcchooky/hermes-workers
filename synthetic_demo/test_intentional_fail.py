from intentional_fail import always_fail


def test_intentional_fail():
    assert always_fail() is True
