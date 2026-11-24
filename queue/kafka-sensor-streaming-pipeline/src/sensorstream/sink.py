"""SQLite sink: results, alerts, dead letters, offsets and operator state.

Results and the consumer offsets/state are written in **one transaction**.
After a crash the consumer resumes exactly from the last committed checkpoint,
and replayed windows are upserted by primary key - so the final table is the
same as if nothing had failed (effectively-once output).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sensorstream.anomaly import Alert
from sensorstream.windowing import WindowResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS window_aggregates (
    sensor_id TEXT NOT NULL,
    window_start REAL NOT NULL,
    window_end REAL NOT NULL,
    site TEXT NOT NULL,
    count INTEGER NOT NULL,
    temp_mean REAL, temp_min REAL, temp_max REAL,
    humidity_mean REAL, vibration_max REAL,
    revision INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (sensor_id, window_start)
);
CREATE TABLE IF NOT EXISTS alerts (
    sensor_id TEXT NOT NULL,
    window_start REAL NOT NULL,
    rule TEXT NOT NULL,
    value REAL,
    detail TEXT,
    PRIMARY KEY (sensor_id, window_start, rule)
);
CREATE TABLE IF NOT EXISTS dead_letters (
    partition INTEGER NOT NULL,
    "offset" INTEGER NOT NULL,
    reason TEXT NOT NULL,
    payload BLOB,
    PRIMARY KEY (partition, "offset")
);
CREATE TABLE IF NOT EXISTS consumer_offsets (
    "group" TEXT NOT NULL,
    partition INTEGER NOT NULL,
    next_offset INTEGER NOT NULL,
    PRIMARY KEY ("group", partition)
);
CREATE TABLE IF NOT EXISTS checkpoints (
    "group" TEXT PRIMARY KEY,
    state TEXT NOT NULL
);
"""

UPSERT_WINDOW = """
INSERT INTO window_aggregates VALUES (?,?,?,?,?,?,?,?,?,?,1)
ON CONFLICT (sensor_id, window_start) DO UPDATE SET
    count = excluded.count, temp_mean = excluded.temp_mean, temp_min = excluded.temp_min,
    temp_max = excluded.temp_max, humidity_mean = excluded.humidity_mean,
    vibration_max = excluded.vibration_max,
    revision = window_aggregates.revision
        + (window_aggregates.count <> excluded.count)
"""


class SQLiteSink:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)

    def commit_batch(
        self,
        group: str,
        windows: list[WindowResult],
        alerts: list[Alert],
        dead: list[tuple[int, int, str, bytes]],
        offsets: dict[int, int],
        state: dict | None,
    ) -> None:
        """Atomically persist outputs together with the consumer position."""
        with self.conn:  # one transaction; rolls back on any exception
            self.conn.executemany(
                UPSERT_WINDOW,
                [
                    (w.sensor_id, w.window_start, w.window_end, w.site, w.count, w.temp_mean,
                     w.temp_min, w.temp_max, w.humidity_mean, w.vibration_max)
                    for w in windows
                ],
            )
            self.conn.executemany(
                "INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?)",
                [(a.sensor_id, a.window_start, a.rule, a.value, a.detail) for a in alerts],
            )
            self.conn.executemany("INSERT OR IGNORE INTO dead_letters VALUES (?,?,?,?)", dead)
            self.conn.executemany(
                'INSERT INTO consumer_offsets VALUES (?,?,?) ON CONFLICT ("group", partition) '
                "DO UPDATE SET next_offset = excluded.next_offset",
                [(group, p, o) for p, o in offsets.items()],
            )
            if state is not None:
                self.conn.execute(
                    "INSERT OR REPLACE INTO checkpoints VALUES (?, ?)", (group, json.dumps(state))
                )

    def load_checkpoint(self, group: str) -> tuple[dict[int, int], dict | None]:
        offsets = dict(
            self.conn.execute(
                'SELECT partition, next_offset FROM consumer_offsets WHERE "group" = ?', (group,)
            ).fetchall()
        )
        row = self.conn.execute(
            'SELECT state FROM checkpoints WHERE "group" = ?', (group,)
        ).fetchone()
        return offsets, (json.loads(row[0]) if row else None)

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self.conn.execute(sql, params).fetchall()

    def close(self) -> None:
        self.conn.close()
