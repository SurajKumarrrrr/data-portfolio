"""Compare the streaming output with a batch ground truth computed from clean data."""

from __future__ import annotations

import pandas as pd

from sensorstream.models import SensorReading
from sensorstream.sink import SQLiteSink


def batch_truth(truth: list[SensorReading], window_s: float) -> pd.DataFrame:
    df = pd.DataFrame([_row(r) for r in truth])
    df["window_start"] = (df["event_ts"] // window_s) * window_s
    return (
        df.groupby(["sensor_id", "window_start"])
        .agg(
            count=("temperature_c", "size"),
            temp_mean=("temperature_c", "mean"),
            temp_max=("temperature_c", "max"),
        )
        .reset_index()
    )


def _row(r: SensorReading) -> dict:
    return {f: getattr(r, f) for f in r.__slots__}


def window_accuracy(sink: SQLiteSink, truth: list[SensorReading], window_s: float) -> dict:
    expected = batch_truth(truth, window_s)
    got = pd.read_sql(
        "SELECT sensor_id, window_start, count, temp_mean, temp_max, revision "
        "FROM window_aggregates",
        sink.conn,
    )
    m = expected.merge(got, on=["sensor_id", "window_start"], how="left", suffixes=("", "_s"))
    exact = (m["count"] == m["count_s"]) & ((m["temp_mean"] - m["temp_mean_s"]).abs() < 1e-3)
    return {
        "expected_windows": len(expected),
        "streamed_windows": len(got),
        "exact_match_pct": round(100 * exact.mean(), 3),
        "windows_missing_events": int((m["count_s"] < m["count"]).sum()),
        "windows_revised_by_late_data": int((got["revision"] > 1).sum()),
        "max_abs_mean_error_c": round(float((m["temp_mean"] - m["temp_mean_s"]).abs().max()), 4),
    }


def alert_quality(
    sink: SQLiteSink, overheat: dict[str, tuple[float, float]], window_s: float
) -> dict:
    """Window-level precision/recall per rule against the injected overheating episodes."""
    positives = {
        (s, ws)
        for s, (start, end) in overheat.items()
        for ws in _window_starts(start, end, window_s)
    }
    out: dict = {"incident_windows": len(positives)}
    for rule in ("static_threshold", "ewma_zscore"):
        rows = sink.query("SELECT sensor_id, window_start FROM alerts WHERE rule = ?", (rule,))
        alerted = {(s, ws) for s, ws in rows}
        tp = len(alerted & positives)
        delays = []
        for s, (start, _) in overheat.items():
            hits = sorted(ws for (ss, ws) in alerted & positives if ss == s)
            if hits:
                delays.append(hits[0] + window_s - start)
        out[rule] = {
            "alerts": len(alerted),
            "precision": round(tp / len(alerted), 3) if alerted else 0.0,
            "recall": round(tp / len(positives), 3) if positives else 0.0,
            "incidents_detected": f"{len(delays)}/{len(overheat)}",
            "mean_event_time_to_alert_s": round(sum(delays) / len(delays), 1) if delays else None,
        }
    return out


def _window_starts(start: float, end: float, window_s: float) -> list[float]:
    """Windows whose majority lies inside [start, end)."""
    first = (start // window_s) * window_s
    out, ws = [], first
    while ws < end:
        overlap = min(ws + window_s, end) - max(ws, start)
        if overlap >= window_s / 2:
            out.append(ws)
        ws += window_s
    return out
