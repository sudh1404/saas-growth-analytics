-- Product-led steps 1-4 are sequential, so each step can never have more accounts than the step before it.
with s as (
    select step_order, count(*) as accounts from {{ ref('fct_funnel_steps') }}
    where step_order <= 4 group by 1
)
select * from (select step_order, accounts, lag(accounts) over (order by step_order) as prev from s) x
where accounts > prev
