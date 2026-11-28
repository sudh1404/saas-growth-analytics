-- D02 | Unit economics by channel: CAC, ARPA, monthly logo churn, LTV, LTV:CAC and CAC payback.
-- Assumptions (documented in docs/metric_definitions.md):
--   * LTV = ARPA x gross margin (80%) / monthly logo churn rate  (steady-state, undiscounted)
--   * ARPA = average MRR over all *active* account-months of the channel (churn-month zeros excluded)
--   * monthly logo churn = churn events / account-months at risk (prev month MRR > 0)
--   * CAC payback (months) = CAC / (ARPA x gross margin)
--   * Organic and referral have no attributable spend, so CAC / LTV:CAC are NULL for them.
with spend as (
    select channel, nullif(sum(spend), 0) as spend, sum(new_customers) as new_customers
    from marts.fct_marketing_daily group by 1
),
paying as (
    select a.acquisition_channel                                                    as channel,
           avg(m.mrr) filter (where m.is_active)                                    as arpa,
           count(*) filter (where m.movement_type = 'churn')::double
             / nullif(count(*) filter (where m.prev_mrr > 0), 0)                    as monthly_churn
    from marts.fct_mrr m join marts.dim_accounts a using (account_id)
    group by 1
)
select
    p.channel,
    s.new_customers,
    round(s.spend, 0)                                          as spend,
    round(s.spend / s.new_customers, 0)                        as cac,
    round(p.arpa, 2)                                           as arpa,
    round(100 * p.monthly_churn, 2)                            as monthly_logo_churn_pct,
    round(1 / p.monthly_churn, 1)                              as expected_lifetime_months,
    round(p.arpa * 0.8 / p.monthly_churn, 0)                   as ltv,
    round(p.arpa * 0.8 / p.monthly_churn / (s.spend / s.new_customers), 2) as ltv_to_cac,
    round((s.spend / s.new_customers) / (p.arpa * 0.8), 1)     as cac_payback_months,
    case when p.arpa * 0.8 / p.monthly_churn / (s.spend / s.new_customers) >= 3 then 'healthy (>=3x)'
         when s.spend is null then 'no paid spend'
         else 'below 3x target' end                            as ltv_cac_assessment
from paying p join spend s using (channel)
order by ltv_to_cac desc nulls last, p.channel;
