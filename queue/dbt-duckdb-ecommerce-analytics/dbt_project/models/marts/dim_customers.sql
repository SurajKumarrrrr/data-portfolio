with order_stats as (
    select
        customer_id,
        min(ordered_at)                                     as first_order_at,
        max(ordered_at)                                     as last_order_at,
        count(*) filter (where status <> 'cancelled')       as lifetime_orders,
        sum(net_revenue)                                    as lifetime_net_revenue
    from {{ ref('fct_orders') }}
    group by customer_id
)

select
    c.customer_id,
    c.first_name,
    c.last_name,
    c.email,
    c.country_code,
    c.signup_at,
    c.has_marketing_opt_in,
    s.first_order_at,
    s.last_order_at,
    coalesce(s.lifetime_orders, 0)                  as lifetime_orders,
    coalesce(s.lifetime_net_revenue, 0)             as lifetime_net_revenue,
    case
        when coalesce(s.lifetime_orders, 0) = 0 then 'prospect'
        when s.lifetime_orders = 1 then 'one_time'
        when s.lifetime_orders <= 3 then 'repeat'
        else 'loyal'
    end                                             as customer_segment
from {{ ref('stg_shop__customers') }} as c
left join order_stats as s using (customer_id)
