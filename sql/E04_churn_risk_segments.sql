-- E04 | Rule-based churn-risk segments of active customers: size, MRR at risk and the drivers present.
-- (The ML model in analysis/churn_model.py produces a probabilistic score; this SQL view is the transparent baseline.)
select
    rule_based_risk,
    count(*)                                                         as customers,
    sum(current_mrr)                                                 as mrr_at_risk,
    round(100.0 * sum(current_mrr) / sum(sum(current_mrr)) over (), 1) as share_of_mrr_pct,
    round(100.0 * avg((coalesce(usage_trend, 1) < 0.7)::int), 1)    as pct_declining_usage,
    round(100.0 * avg((failed_payment_attempts_90d > 0)::int), 1)   as pct_recent_failed_payment,
    round(100.0 * avg((support_tickets_90d >= 2)::int), 1)          as pct_2plus_tickets_90d,
    round(100.0 * avg((not is_activated)::int), 1)                  as pct_not_activated,
    round(100.0 * avg((tenure_months < 3)::int), 1)                 as pct_new_customers
from marts.agg_customer_segments
group by 1
order by case rule_based_risk when 'High' then 1 when 'Medium' then 2 else 3 end;
