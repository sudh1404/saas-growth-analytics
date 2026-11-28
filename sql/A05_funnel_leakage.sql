-- A05 | Funnel leakage: for every channel, which stage loses the most prospects (absolute and relative)?
-- Leakage at a stage = accounts that reached the previous stage but not this one.
with mature as (
    select * from marts.dim_accounts where signup_date <= date '2025-12-17'
),
traffic as (
    select channel as acquisition_channel, sum(visitors) as visitors
    from marts.fct_marketing_daily where date <= date '2025-12-17' group by 1
),
stages as (
    select acquisition_channel, 1 as stage_order, 'Visit -> Signup' as transition,
           max(t.visitors) as entered, count(*) as reached
    from mature join traffic t using (acquisition_channel) group by 1
    union all
    select acquisition_channel, 2, 'Signup -> Onboarded', count(*), count(*) filter (where is_onboarded) from mature group by 1
    union all
    select acquisition_channel, 3, 'Onboarded -> Project', count(*) filter (where is_onboarded),
           count(*) filter (where is_onboarded and has_created_project) from mature group by 1
    union all
    select acquisition_channel, 4, 'Project -> Activated', count(*) filter (where has_created_project),
           count(*) filter (where has_created_project and is_activated) from mature group by 1
    union all
    select acquisition_channel, 5, 'Activated -> Paid', count(*) filter (where is_activated),
           count(*) filter (where is_activated and is_paying_customer) from mature group by 1
)
select
    acquisition_channel,
    stage_order,
    transition,
    entered,
    reached,
    entered - reached                                        as leaked,
    round(100.0 * (entered - reached) / entered, 1)          as leak_pct,
    case when stage_order > 1 then
        rank() over (partition by acquisition_channel, stage_order > 1
                     order by (entered - reached) * 1.0 / entered desc)
    end                                                      as in_product_leak_rank   -- 1 = worst post-signup leak
from stages
order by acquisition_channel, stage_order;
