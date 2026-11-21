from datetime import date

import pytest

from retail_kpi import kpis
from retail_kpi.db import connect, filter_options
from retail_kpi.filters import Filters

FEB = Filters(date(2025, 2, 1), date(2025, 2, 28))
ALL = Filters(date(2025, 1, 1), date(2025, 2, 28))


def test_summary_matches_hand_computed_values(con):
    s = kpis.kpi_summary(con, FEB)
    assert s.net_revenue == pytest.approx(28.0)
    assert s.gross_revenue == pytest.approx(78.0)
    assert s.orders == 2
    assert s.customers == 2
    assert s.units == 3
    assert s.avg_order_value == pytest.approx(14.0)
    assert s.gross_margin_pct == pytest.approx(round(100 * 10 / 28, 2))
    assert s.return_rate_pct == pytest.approx(round(100 * 50 / 78, 2))


def test_summary_with_no_matching_rows_is_zero_not_error(con):
    s = kpis.kpi_summary(con, Filters(date(2030, 1, 1), date(2030, 1, 2)))
    assert s.orders == 0
    assert s.net_revenue == 0
    assert s.avg_order_value == 0
    assert s.gross_margin_pct == 0


def test_category_filter_applies_at_line_level(con):
    toys = kpis.kpi_summary(con, Filters(FEB.start, FEB.end, categories=("Toys",)))
    assert toys.net_revenue == pytest.approx(28.0)
    assert toys.return_rate_pct == 0
    fashion = kpis.kpi_summary(con, Filters(FEB.start, FEB.end, categories=("Fashion",)))
    assert fashion.net_revenue == 0
    assert fashion.return_rate_pct == 100


def test_deltas_vs_previous_period(con):
    # Feb 2025 has 28 days -> previous period is 2025-01-04 .. 2025-01-31 (orders 1 and 2)
    d = kpis.kpi_deltas(con, FEB)
    # Jan net = 10 + 50 = 60 ; Feb net = 28
    assert d["net_revenue"] == pytest.approx(round(100 * (28 - 60) / 60, 2))
    assert d["orders"] == 0.0
    jan_margin = 100 * (60 - 26) / 60
    assert d["gross_margin_pct"] == pytest.approx(round(100 * 10 / 28, 2) - round(jan_margin, 2))


def test_deltas_without_baseline_are_none(con):
    d = kpis.kpi_deltas(con, Filters(date(2025, 1, 1), date(2025, 1, 31)))
    assert d["net_revenue"] is None
    assert d["return_rate_pct"] is None


def test_pct_change():
    assert kpis.pct_change(110, 100) == 10.0
    assert kpis.pct_change(5, 0) is None


def test_revenue_trend_monthly(con):
    t = kpis.revenue_trend(con, ALL, "month")
    assert [str(p) for p in t["period"].dt.date] == ["2025-01-01", "2025-02-01"]
    assert t["net_revenue"].tolist() == pytest.approx([60.0, 28.0])
    assert t["orders"].tolist() == [2, 2]


def test_revenue_trend_rejects_unknown_grain(con):
    with pytest.raises(ValueError):
        kpis.revenue_trend(con, ALL, "hour; DROP TABLE orders")


def test_top_products_ordering_and_limit(con):
    top = kpis.top_products(con, ALL, n=1)
    assert len(top) == 1
    assert top.iloc[0]["product_name"] == "B"  # 50 net vs A's 38
    full = kpis.top_products(con, ALL, n=10)
    assert full["net_revenue"].tolist() == pytest.approx([50.0, 38.0])
    assert full.loc[full["product_name"] == "B", "return_rate_pct"].iloc[0] == pytest.approx(50.0)


def test_breakdown_shares_sum_to_100(con):
    b = kpis.breakdown(con, ALL, "channel")
    assert b["share_pct"].sum() == pytest.approx(100.0)
    assert set(b["channel"]) == {"store", "online"}


def test_breakdown_rejects_unknown_dimension(con):
    with pytest.raises(ValueError):
        kpis.breakdown(con, ALL, "customer_id")


def test_weekday_profile(con):
    w = kpis.weekday_profile(con, ALL)
    # 2025-02-09 is a Sunday (ISO 7): only the online order
    sunday = w[w["weekday"] == 7]
    assert sunday["channel"].tolist() == ["online"]
    assert sunday["avg_net_revenue"].iloc[0] == pytest.approx(10.0)


def test_filter_options(con):
    opts = filter_options(con)
    assert opts["date_range"] == [date(2025, 1, 10), date(2025, 2, 9)]
    assert opts["regions"] == ["Online", "West"]
    assert opts["categories"] == ["Fashion", "Toys"]


def test_connect_missing_files_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        connect(tmp_path)
