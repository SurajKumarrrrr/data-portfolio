-- Share of each first-order cohort that orders again N months later.
with customer_months as (
    select distinct
        customer_id,
        cast(date_trunc('month', order_date) as date) as activity_month
    from {{ ref('fct_orders') }}
    where status <> 'cancelled'
),

cohorts as (
    select customer_id, min(activity_month) as cohort_month
    from customer_months
    group by customer_id
),

cohort_sizes as (
    select cohort_month, count(*) as cohort_size
    from cohorts
    group by cohort_month
)

select
    c.cohort_month,
    datediff('month', c.cohort_month, cm.activity_month)        as months_since_first_order,
    s.cohort_size,
    count(distinct cm.customer_id)                              as active_customers,
    round(count(distinct cm.customer_id) / s.cohort_size, 4)    as retention_rate
from cohorts as c
inner join customer_months as cm using (customer_id)
inner join cohort_sizes as s using (cohort_month)
group by c.cohort_month, months_since_first_order, s.cohort_size
order by 1, 2
