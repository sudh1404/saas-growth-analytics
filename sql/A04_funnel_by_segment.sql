-- A04 | Funnel conversion by country, company size and customer segment (mature signups only).
-- One query, long format: dimension | value | stage rates. Window function ranks values within each dimension.
with base as (
    select * from marts.dim_accounts where signup_date <= date '2025-12-17'
),
long as (
    select 'country'          as dimension, country          as value, is_onboarded, is_activated, is_paying_customer from base
    union all
    select 'company_size'     as dimension, company_size     as value, is_onboarded, is_activated, is_paying_customer from base
    union all
    select 'customer_segment' as dimension, customer_segment as value, is_onboarded, is_activated, is_paying_customer from base
),
agg as (
    select dimension, value,
           count(*)                                   as signups,
           avg(is_onboarded::int)                     as onboard_rate,
           avg(is_activated::int)                     as activation_rate,
           avg(is_paying_customer::int)               as paid_rate
    from long
    group by 1, 2
)
select
    dimension,
    value,
    signups,
    round(100 * onboard_rate, 1)     as onboarded_pct,
    round(100 * activation_rate, 1)  as activated_pct,
    round(100 * paid_rate, 1)        as signup_to_paid_pct,
    round(100 * (paid_rate - avg(paid_rate) over (partition by dimension)), 1) as paid_pct_vs_dimension_avg,
    rank() over (partition by dimension order by paid_rate desc)               as rank_in_dimension
from agg
where value <> 'Unknown'
order by dimension, rank_in_dimension;
