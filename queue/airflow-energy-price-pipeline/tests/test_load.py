from datetime import date

import pytest

from energy_pipeline.load import connect, load_day
from energy_pipeline.sources import SyntheticSmardSource
from energy_pipeline.transform import to_records


def records_for(d: date):
    return to_records(SyntheticSmardSource().fetch_day(d), d)


@pytest.fixture
def con():
    c = connect(":memory:")
    yield c
    c.close()


def test_load_is_idempotent(con):
    d = date(2025, 3, 5)
    first = load_day(con, records_for(d), d, "synthetic")
    second = load_day(con, records_for(d), d, "synthetic")
    assert first == {"deleted": 0, "inserted": 24}
    assert second == {"deleted": 24, "inserted": 24}
    assert con.execute("SELECT count(*) FROM hourly_prices").fetchone()[0] == 24
    assert con.execute("SELECT count(*) FROM daily_price_stats").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM load_audit").fetchone()[0] == 2


def test_reload_only_touches_its_partition(con):
    d1, d2 = date(2025, 3, 5), date(2025, 3, 6)
    load_day(con, records_for(d1), d1, "synthetic")
    load_day(con, records_for(d2), d2, "synthetic")
    load_day(con, records_for(d1), d1, "synthetic")
    rows = con.execute("SELECT delivery_date, count(*) FROM hourly_prices GROUP BY 1 ORDER BY 1").fetchall()
    assert rows == [(d1, 24), (d2, 24)]


def test_daily_stats_match_python(con):
    d = date(2025, 3, 5)  # Wednesday
    recs = records_for(d)
    load_day(con, recs, d, "synthetic")
    base, peak, offpeak, lo, hi, neg, n = con.execute(
        "SELECT base_avg, peak_avg, offpeak_avg, min_price, max_price, negative_hours, n_hours "
        "FROM daily_price_stats"
    ).fetchone()
    prices = [r.price_eur_mwh for r in recs]
    peak_prices = [r.price_eur_mwh for r in recs if 8 <= r.local_hour <= 19]
    off_prices = [r.price_eur_mwh for r in recs if not 8 <= r.local_hour <= 19]
    assert base == pytest.approx(sum(prices) / 24, abs=0.006)
    assert peak == pytest.approx(sum(peak_prices) / 12, abs=0.006)
    assert offpeak == pytest.approx(sum(off_prices) / 12, abs=0.006)
    assert (lo, hi, n) == (min(prices), max(prices), 24)
    assert neg == sum(p < 0 for p in prices)


def test_weekend_has_no_peak(con):
    d = date(2025, 3, 8)  # Saturday
    load_day(con, records_for(d), d, "synthetic")
    peak, offpeak = con.execute("SELECT peak_avg, offpeak_avg FROM daily_price_stats").fetchone()
    assert peak is None and offpeak is not None


def test_failed_insert_rolls_back(con):
    d = date(2025, 3, 5)
    load_day(con, records_for(d), d, "synthetic")
    recs = records_for(d)
    dup = recs + [recs[0]]  # primary key violation mid-transaction
    with pytest.raises(Exception):
        load_day(con, dup, d, "synthetic")
    assert con.execute("SELECT count(*) FROM hourly_prices").fetchone()[0] == 24
    assert con.execute("SELECT count(*) FROM daily_price_stats").fetchone()[0] == 1


def test_rejects_records_from_other_day(con):
    with pytest.raises(ValueError):
        load_day(con, records_for(date(2025, 3, 5)), date(2025, 3, 6), "synthetic")
