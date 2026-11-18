-- The extractor re-delivers orders when their status changes. Keep the latest version.
with source as (
    select * from {{ source('shop', 'orders') }}
),

typed as (
    select
        cast(order_id as integer)                               as order_id,
        cast(customer_id as integer)                            as customer_id,
        cast(order_ts as timestamp)                             as ordered_at,
        lower(trim(status))                                     as status,
        upper(trim(shipping_country))                           as shipping_country,
        {{ cents_to_eur('cast(shipping_cents as integer)') }}   as shipping_amount,
        cast(_loaded_at as timestamp)                           as source_loaded_at
    from source
)

select * exclude (row_num)
from (
    select
        *,
        row_number() over (partition by order_id order by source_loaded_at desc) as row_num
    from typed
)
where row_num = 1
