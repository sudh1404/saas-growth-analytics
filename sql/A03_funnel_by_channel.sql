-- A03 | Funnel conversion by acquisition channel (mature signups only), including visit -> signup.
with traffic as (
    select channel as acquisition_channel, sum(visitors) as visitors
    from marts.fct_marketing_daily where date <= date '2025-12-17' group by 1
),
f as (
    select
        acquisition_channel,
        count(*)                                     as signups,
        count(*) filter (where is_onboarded)         as onboarded,
        count(*) filter (where is_activated)         as activated,
        count(*) filter (where is_paying_customer)   as paying,
        count(*) filter (where is_activated and is_paying_customer) as activated_paying
    from marts.dim_accounts
    where signup_date <= date '2025-12-17'
    group by 1
)
select
    acquisition_channel,
    t.visitors,
    signups,
    round(100.0 * signups   / t.visitors, 2)   as visit_to_signup_pct,
    round(100.0 * onboarded / signups, 1)      as signup_to_onboarded_pct,
    round(100.0 * activated / onboarded, 1)    as onboarded_to_activated_pct,
    round(100.0 * activated_paying / activated, 1)          as activated_to_paid_pct,
    round(100.0 * (paying - activated_paying) / paying, 1)  as pct_payers_never_activated,
    round(100.0 * paying    / signups, 1)      as signup_to_paid_pct,
    round(100.0 * paying    / t.visitors, 3)   as visit_to_paid_pct,
    rank() over (order by paying * 1.0 / signups desc) as rank_signup_to_paid
from f
join traffic t using (acquisition_channel)
order by signup_to_paid_pct desc;
