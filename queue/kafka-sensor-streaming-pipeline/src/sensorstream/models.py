"""Message schema for sensor readings and (de)serialisation helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

METRICS: tuple[str, ...] = ("temperature_c", "humidity_pct", "vibration_mm_s")


class InvalidMessage(ValueError):
    """Raised when a raw message cannot be turned into a SensorReading."""


@dataclass(frozen=True, slots=True)
class SensorReading:
    """One measurement emitted by a sensor.

    ``event_ts`` is the time the measurement was taken (epoch seconds), which is
    what windows are based on - not the time the message reached the broker.
    ``seq`` is a per-sensor monotonically increasing counter used for dedup.
    """

    sensor_id: str
    site: str
    seq: int
    event_ts: float
    temperature_c: float
    humidity_pct: float
    vibration_mm_s: float

    def to_bytes(self) -> bytes:
        return json.dumps(asdict(self), separators=(",", ":")).encode()

    @property
    def key(self) -> bytes:
        """Partition key: all readings of one sensor land in one partition (ordering)."""
        return self.sensor_id.encode()


def parse_reading(raw: bytes) -> SensorReading:
    """Parse and validate a raw message. Raises InvalidMessage on any problem."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidMessage(f"not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidMessage("payload is not a JSON object")

    required = {"sensor_id", "site", "seq", "event_ts", *METRICS}
    missing = required - data.keys()
    if missing:
        raise InvalidMessage(f"missing fields: {sorted(missing)}")

    try:
        reading = SensorReading(
            sensor_id=str(data["sensor_id"]),
            site=str(data["site"]),
            seq=int(data["seq"]),
            event_ts=float(data["event_ts"]),
            temperature_c=float(data["temperature_c"]),
            humidity_pct=float(data["humidity_pct"]),
            vibration_mm_s=float(data["vibration_mm_s"]),
        )
    except (TypeError, ValueError) as exc:
        raise InvalidMessage(f"bad field type: {exc}") from exc

    if not -50.0 <= reading.temperature_c <= 150.0:
        raise InvalidMessage(f"temperature out of physical range: {reading.temperature_c}")
    if not 0.0 <= reading.humidity_pct <= 100.0:
        raise InvalidMessage(f"humidity out of range: {reading.humidity_pct}")
    if reading.vibration_mm_s < 0:
        raise InvalidMessage(f"negative vibration: {reading.vibration_mm_s}")
    return reading
