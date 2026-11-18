-- Calendar dimension spanning the full order history.
{% set start_date = "2024-01-01" %}
{% set end_date = "2025-12-31" %}

select
    cast(d as date)                         as date_day,
    year(d)                                 as year,
    quarter(d)                              as quarter,
    month(d)                                as month,
    strftime(d, '%B')                       as month_name,
    cast(date_trunc('month', d) as date)    as month_start,
    weekofyear(d)                           as iso_week,
    isodow(d)                               as iso_day_of_week,
    isodow(d) in (6, 7)                     as is_weekend
from generate_series(date '{{ start_date }}', date '{{ end_date }}', interval 1 day) as t(d)
