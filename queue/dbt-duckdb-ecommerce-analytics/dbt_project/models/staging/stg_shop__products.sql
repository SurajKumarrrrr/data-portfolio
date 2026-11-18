with source as (
    select * from {{ source('shop', 'products') }}
)

select
    cast(product_id as integer)                         as product_id,
    sku,
    product_name,
    category,
    {{ cents_to_eur('cast(unit_price_cents as integer)') }} as list_price,
    {{ cents_to_eur('cast(unit_cost_cents as integer)') }}  as unit_cost,
    {{ parse_bool('is_active') }}                       as is_active
from source
