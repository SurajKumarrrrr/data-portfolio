-- Every non-cancelled order must have been paid exactly its computed total
-- (items - discounts + shipping). Catches pricing/shipping logic drift.
select order_id, order_total, paid_amount
from {{ ref('fct_orders') }}
where status <> 'cancelled'
  and abs(paid_amount - order_total) > 0.01
