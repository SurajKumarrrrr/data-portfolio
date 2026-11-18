select o.order_id, o.ordered_at, c.signup_at
from {{ ref('fct_orders') }} as o
inner join {{ ref('dim_customers') }} as c using (customer_id)
where o.ordered_at < c.signup_at
