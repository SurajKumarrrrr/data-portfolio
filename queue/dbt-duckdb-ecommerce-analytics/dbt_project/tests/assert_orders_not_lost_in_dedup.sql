-- Deduplication must keep exactly one row per distinct source order_id.
select *
from (
    select
        (select count(distinct order_id) from {{ source('shop', 'orders') }}) as source_orders,
        (select count(*) from {{ ref('fct_orders') }})                        as fact_orders
)
where source_orders <> fact_orders
