with source as (
    select * from {{ source('shop', 'order_items') }}
)

select
    cast(order_item_id as integer)                              as order_item_id,
    cast(order_id as integer)                                   as order_id,
    cast(product_id as integer)                                 as product_id,
    cast(quantity as integer)                                   as quantity,
    {{ cents_to_eur('cast(unit_price_cents as integer)') }}     as unit_price,
    {{ cents_to_eur('cast(discount_cents as integer)') }}       as discount_amount
from source
