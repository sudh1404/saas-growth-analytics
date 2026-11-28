-- C02 | ARPA (MRR per paying account) and ARPU (MRR per active seat), monthly and by plan at the snapshot.
-- ARPU uses the latest known seat count per account; accounts with no usage data yet are excluded.
select 'monthly' as view, cast(month as varchar) as label,
       active_customers as accounts, round(mrr, 0) as mrr,
       round(arpa, 2) as arpa, active_seats as seats, round(arpu, 2) as arpu
from marts.agg_kpis_monthly
union all
select 'by_plan_at_snapshot', p.plan_name,
       count(*), sum(m.mrr), round(avg(m.mrr), 2), sum(m.active_seats),
       round(sum(m.mrr) filter (where m.active_seats is not null) / sum(m.active_seats), 2)
from marts.fct_mrr m join marts.dim_plans p using (plan_id)
where m.month = date '2025-12-01' and m.is_active
group by p.plan_name, p.monthly_price
order by view, label;
