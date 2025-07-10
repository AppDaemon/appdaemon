from datetime import timedelta

from appdaemon import utils


def test_parse_timedelta() -> None:
    """Test the parsing of timedelta strings."""
    parser = utils.parse_timedelta

    assert parser(None) == timedelta()

    assert parser(1) == timedelta(seconds=1)
    assert parser(123) == timedelta(minutes=2, seconds=3)
    assert parser(3600) == timedelta(hours=1)

    assert parser("01") == timedelta(seconds=1)
    assert parser("01:00") == timedelta(minutes=1)
    assert parser("01:00:00") == timedelta(hours=1)

    assert parser("1.234567") == timedelta(seconds=1, microseconds=234567)
    assert parser("   1.2   :   3.7    ") == timedelta(minutes=1.2, seconds=3.7)
    assert parser("1.2:3.4:5.6") == timedelta(hours=1.2, minutes=3.4, seconds=5.6)

    assert parser("1:0:0") == timedelta(hours=1)
    assert parser("1:0:0.123456") == timedelta(hours=1, microseconds=123456)
    assert parser("1:0.123456") == timedelta(minutes=1, microseconds=123456)
    assert parser("3s") == timedelta(seconds=3)
    assert parser("2m 3s") == timedelta(minutes=2, seconds=3)
    assert parser("1h 2m 3s") == timedelta(hours=1, minutes=2, seconds=3)
