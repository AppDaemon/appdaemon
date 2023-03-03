from appdaemon.__main__ import ADMain


# TODO: fake test to assert that pytest works correctly


def test_main():
    main = ADMain()
    assert main is not None
