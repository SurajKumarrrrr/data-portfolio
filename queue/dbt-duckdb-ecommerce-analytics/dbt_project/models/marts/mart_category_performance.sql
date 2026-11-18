select
    category,
    sum(quantity) filter (where order_status <> 'cancelled')               as units_sold,
    round(sum(recognised_revenue), 2)                                       as net_revenue,
    round(sum(recognised_margin), 2)                                        as gross_margin,
    round(100 * sum(recognised_margin) / nullif(sum(recognised_revenue), 0), 1)
                                                                            as gross_margin_pct,
    round(100.0 * count(*) filter (where order_status = 'returned')
          / nullif(count(*) filter (where order_status <> 'cancelled'), 0), 1)
                                                                            as return_rate_pct
from {{ ref('fct_order_items') }}
group by category
order by net_revenue desc
