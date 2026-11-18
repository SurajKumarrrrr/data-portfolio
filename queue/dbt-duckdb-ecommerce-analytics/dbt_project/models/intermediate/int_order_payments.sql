-- Payment events rolled up to one row per order.
select
    order_id,
    sum(amount) filter (where payment_status = 'success')       as paid_amount,
    sum(amount) filter (where payment_status = 'refunded')      as refunded_amount,
    count(*) filter (where payment_status = 'failed')           as failed_payment_attempts,
    arg_min(payment_method, created_at)
        filter (where payment_status = 'success')               as payment_method
from {{ ref('stg_shop__payments') }}
group by order_id
