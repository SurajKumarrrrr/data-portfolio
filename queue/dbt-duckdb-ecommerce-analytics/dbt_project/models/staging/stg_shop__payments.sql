with source as (
    select * from {{ source('shop', 'payments') }}
)

select
    cast(payment_id as integer)                         as payment_id,
    cast(order_id as integer)                           as order_id,
    lower(payment_method)                               as payment_method,
    lower(status)                                       as payment_status,
    {{ cents_to_eur('cast(amount_cents as integer)') }} as amount,
    cast(created_at as timestamp)                       as created_at
from source
