-- Grain: one row per order line, with order context for slicing.
select
    i.order_item_id,
    i.order_id,
    o.customer_id,
    i.product_id,
    o.order_date,
    o.status                                                        as order_status,
    i.category,
    i.quantity,
    i.unit_price,
    i.gross_amount,
    i.discount_amount,
    i.net_amount,
    i.cost_amount,
    case when o.is_revenue_order then i.net_amount else 0 end      as recognised_revenue,
    case when o.is_revenue_order then i.net_amount - i.cost_amount else 0 end
                                                                    as recognised_margin
from {{ ref('int_order_items_enriched') }} as i
inner join {{ ref('fct_orders') }} as o using (order_id)
