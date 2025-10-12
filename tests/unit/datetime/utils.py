import itertools
from datetime import timedelta
from typing import Any

from appdaemon import utils


def _process_params(params: dict[str, list[Any]]) -> tuple[tuple[str, ...], list[tuple[Any, ...]]]:
    return tuple(params.keys()), list(itertools.product(*params.values()))


class ParameterBuilder:
    """Helper class for building pytest parametrize arguments."""

    @staticmethod
    def offsets() -> dict[Any, timedelta]:
        return {
            None: timedelta(),
            1: timedelta(seconds=1),
            10: timedelta(seconds=10),
            3600: timedelta(hours=1),
            "1.234567": timedelta(seconds=1, microseconds=234567),
            "05:00": timedelta(minutes=5),
            "   1.2   :   3.7    ": timedelta(minutes=1.2, seconds=3.7),
            "1.5:00:00": timedelta(hours=1, minutes=30),
            "1.2:3.4:5.6": timedelta(hours=1.2, minutes=3.4, seconds=5.6),
            "3s": timedelta(seconds=3),
            "2m 3s": timedelta(minutes=2, seconds=3),
            "1h 2m 3s": timedelta(hours=1, minutes=2, seconds=3),
        }

    @staticmethod
    def hour_params() -> tuple[tuple[str, ...], list[tuple[Any, ...]]]:
        hour_params = {
            "input_": [f"{i:02}:00" for i in range(0, 24, 6)],
            "aware": [True, False],
            "today": [True, False]
        }  # fmt: skip
        return _process_params(hour_params)

    @staticmethod
    def sun_params() -> tuple[tuple[str, ...], list[tuple[Any, ...]]]:
        """Creates sets of kwargs for ``now_str``, ``when``, and ``input_`` for ``test_parse_sun_offsets``."""
        offsets = [str(utils.parse_timedelta(t)) for t in [1, timedelta(minutes=30), timedelta(hours=1)]]
        src = {
            "str_offset": offsets,
            "sign": [True, False],
            "today": [True, False],
            "aware": [True, False],
        }
        sunrise_params = list(itertools.product(*src.values()))
        sunrise_params = (
            (f"sunrise {'+' if sign else '-'} {offset}", today, aware)
            for offset, sign, today, aware in sunrise_params
        )  # fmt: skip
        sunrise_params = (("input_", "today", "aware"), list(sunrise_params))

        offsets = [timedelta(seconds=1), timedelta(minutes=1), timedelta(hours=1.5)]
        offsets = [td.total_seconds() for td in offsets]
        offsets = [(n * s) for n, s in itertools.product(offsets, [1, -1])]
        offsets = sorted(offsets)

        sun_params = itertools.product(["sunrise", "sunset"], offsets)
        sun_params = {
            "now_str": ["early", "midday", "late"],
            "when": ["today", "next"],
            "input_": [
                f'{type_} {"+" if str_offset > 0 else "-"} {utils.parse_timedelta(abs(str_offset))}'
                for type_, str_offset in sun_params
            ],
        }
        return _process_params(sun_params)
