-- C01 | MRR bridge with ARR, Net New MRR and growth rate, plus an explicit reconciliation check.
-- Closing MRR = Opening + New + Expansion + Reactivation + Contraction + Churned (contraction/churn are negative).
select
    month,
    opening_mrr,
    new_mrr,
    expansion_mrr,
    reactivation_mrr,
    contraction_mrr,
    churned_mrr,
    net_new_mrr,
    closing_mrr,
    closing_mrr * 12                                                     as arr,
    round(100.0 * net_new_mrr / nullif(opening_mrr, 0), 2)               as mrr_growth_pct,
    round(100.0 * (expansion_mrr + contraction_mrr + churned_mrr) / nullif(opening_mrr, 0), 2) as existing_base_net_pct,
    opening_mrr + new_mrr + expansion_mrr + reactivation_mrr + contraction_mrr + churned_mrr - closing_mrr
                                                                         as reconciliation_diff   -- must be 0
from marts.agg_mrr_bridge_monthly
order by month;
