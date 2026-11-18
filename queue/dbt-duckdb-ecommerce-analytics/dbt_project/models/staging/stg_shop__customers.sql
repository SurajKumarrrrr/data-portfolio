with source as (
    select * from {{ source('shop', 'customers') }}
)

select
    cast(customer_id as integer)                as customer_id,
    trim(first_name)                            as first_name,
    trim(last_name)                             as last_name,
    lower(trim(email))                          as email,
    upper(trim(country_code))                   as country_code,
    cast(signup_at as timestamp)                as signup_at,
    {{ parse_bool('marketing_opt_in') }}        as has_marketing_opt_in
from source
