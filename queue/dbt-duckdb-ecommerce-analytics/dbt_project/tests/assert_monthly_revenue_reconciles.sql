-- The monthly mart must add up to the order fact (no orders lost outside dim_date).
select mart_total, fact_total
from (
    select
        (select sum(net_revenue) from {{ ref('mart_monthly_revenue') }}) as mart_total,
        (select sum(net_revenue) from {{ ref('fct_orders') }})           as fact_total
)
where abs(mart_total - fact_total) > 0.01
