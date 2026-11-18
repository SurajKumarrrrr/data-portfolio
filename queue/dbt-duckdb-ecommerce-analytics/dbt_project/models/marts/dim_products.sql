select
    product_id,
    sku,
    product_name,
    category,
    list_price,
    unit_cost,
    round(1 - unit_cost / nullif(list_price, 0), 4) as list_margin_pct,
    is_active
from {{ ref('stg_shop__products') }}
