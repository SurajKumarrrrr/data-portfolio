-- Monthly business KPIs, one row per calendar month (months without orders show zeros).
with months as (
    select distinct month_start from {{ ref('dim_date') }}
),

orders as (
    select
        cast(date_trunc('month', order_date) as date) as month_start,
        *
    from {{ ref('fct_orders') }}
),

agg as (
    select
        month_start,
        count(*)                                            as orders,
        count(*) filter (where is_revenue_order)            as revenue_orders,
        sum(net_revenue)                                    as net_revenue,
        count(distinct customer_id) filter (where status <> 'cancelled')
                                                            as active_customers,
        count(*) filter (where customer_order_number = 1)   as new_customers
    from orders
    group by month_start
)

select
    m.month_start,
    coalesce(a.orders, 0)                                       as orders,
    coalesce(a.revenue_orders, 0)                               as revenue_orders,
    cast(coalesce(a.net_revenue, 0) as decimal(14, 2))           as net_revenue,
    round(a.net_revenue / nullif(a.revenue_orders, 0), 2)       as avg_order_value,
    coalesce(a.active_customers, 0)                             as active_customers,
    coalesce(a.new_customers, 0)                                as new_customers,
    coalesce(a.active_customers, 0) - coalesce(a.new_customers, 0) as returning_customers
from months as m
left join agg as a using (month_start)
order by m.month_start
