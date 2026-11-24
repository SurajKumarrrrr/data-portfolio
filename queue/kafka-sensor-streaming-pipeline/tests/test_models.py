import json

import pytest

from sensorstream.models import InvalidMessage, parse_reading


def test_roundtrip(make_reading):
    r = make_reading(seq=3, ts=12.5)
    assert parse_reading(r.to_bytes()) == r
    assert r.key == b"s1"


@pytest.mark.parametrize(
    "raw",
    [
        b"{not json",
        b"[1, 2]",
        json.dumps({"sensor_id": "x"}).encode(),
        b"\xff\xfe",
    ],
)
def test_malformed_payloads_rejected(raw):
    with pytest.raises(InvalidMessage):
        parse_reading(raw)


@pytest.mark.parametrize(
    "field,value", [("temperature_c", 500), ("humidity_pct", -1), ("vibration_mm_s", -0.1),
                    ("seq", "abc")]
)
def test_out_of_range_rejected(make_reading, field, value):
    data = json.loads(make_reading().to_bytes())
    data[field] = value
    with pytest.raises(InvalidMessage):
        parse_reading(json.dumps(data).encode())
