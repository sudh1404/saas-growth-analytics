-- C04 | MRR, customers and revenue share by subscription plan each quarter-end month, plus plan mix of new customers.
with q as (
    select m.month, p.plan_name, p.monthly_price,
           count(*) filter (where m.is_active)                        as customers,
           sum(m.mrr)                                                 as mrr,
           count(*) filter (where m.movement_type = 'new')            as new_customers
    from marts.fct_mrr m join marts.dim_plans p using (plan_id)
    where month(m.month) in (3, 6, 9, 12)
    group by 1, 2, 3
)
select
    month,
    plan_name,
    customers,
    mrr,
    round(100.0 * mrr / sum(mrr) over (partition by month), 1)                     as mrr_share_pct,
    round(100.0 * customers / sum(customers) over (partition by month), 1)         as customer_share_pct,
    round(100.0 * mrr / lag(mrr) over (partition by plan_name order by month) - 100, 1) as qoq_mrr_growth_pct
from q
order by month, monthly_price;
