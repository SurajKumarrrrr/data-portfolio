-- Grain: one row per order (latest status). Monetary columns in EUR.
with items as (
    select
        order_id,
        count(*)                as line_count,
        sum(quantity)           as units,
        sum(gross_amount)       as gross_item_amount,
        sum(discount_amount)    as discount_amount,
        sum(net_amount)         as net_item_amount,
        sum(cost_amount)        as cost_amount
    from {{ ref('int_order_items_enriched') }}
    group by order_id
),

orders as (
    select
        o.order_id,
        o.customer_id,
        cast(o.ordered_at as date)                                  as order_date,
        o.ordered_at,
        o.status,
        o.shipping_country,
        coalesce(p.payment_method, 'none')                          as payment_method,
        i.line_count,
        i.units,
        i.gross_item_amount,
        i.discount_amount,
        o.shipping_amount,
        i.net_item_amount + o.shipping_amount                       as order_total,
        i.cost_amount,
        coalesce(p.paid_amount, 0)                                  as paid_amount,
        coalesce(p.refunded_amount, 0)                              as refunded_amount,
        coalesce(p.paid_amount, 0) - coalesce(p.refunded_amount, 0) as net_revenue,
        coalesce(p.failed_payment_attempts, 0)                      as failed_payment_attempts,
        o.status in ('placed', 'shipped', 'delivered')              as is_revenue_order
    from {{ ref('stg_shop__orders') }} as o
    inner join items as i using (order_id)
    left join {{ ref('int_order_payments') }} as p using (order_id)
)

select
    *,
    case when status = 'cancelled' then null
         else row_number() over (
             partition by customer_id, status = 'cancelled' order by ordered_at, order_id)
    end as customer_order_number
from orders
