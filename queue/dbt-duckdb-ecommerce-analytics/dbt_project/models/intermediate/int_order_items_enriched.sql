-- Order lines priced and costed, one row per order item.
select
    oi.order_item_id,
    oi.order_id,
    oi.product_id,
    p.category,
    oi.quantity,
    oi.unit_price,
    oi.quantity * oi.unit_price                         as gross_amount,
    oi.discount_amount,
    oi.quantity * oi.unit_price - oi.discount_amount    as net_amount,
    oi.quantity * p.unit_cost                           as cost_amount
from {{ ref('stg_shop__order_items') }} as oi
inner join {{ ref('stg_shop__products') }} as p using (product_id)
