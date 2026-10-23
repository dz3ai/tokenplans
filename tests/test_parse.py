import pytest

import tokenplans.balance.parse as parse


def test_simple_dotted():
    assert parse.extract_value({"data": {"available": 12.5}}, "data.available") == 12.5


def test_array_index():
    data = {"balance_infos": [{"total_balance": "100.00", "currency": "CNY"}]}
    assert parse.extract_value(data, "balance_infos[0].total_balance") == "100.00"


def test_missing_key_raises():
    with pytest.raises(KeyError):
        parse.extract_value({}, "nope")


def test_bad_segment_raises():
    with pytest.raises(ValueError):
        parse.extract_value({}, "a..b")
