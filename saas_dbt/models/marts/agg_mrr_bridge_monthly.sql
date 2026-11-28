-- Company-level MRR bridge. Opening MRR + new + expansion + reactivation + contraction + churned = closing MRR.
select
    month,
    sum(prev_mrr)                                                          as opening_mrr,
    coalesce(sum(case when movement_type = 'new'          then mrr_change end), 0) as new_mrr,
    coalesce(sum(case when movement_type = 'expansion'    then mrr_change end), 0) as expansion_mrr,
    coalesce(sum(case when movement_type = 'reactivation' then mrr_change end), 0) as reactivation_mrr,
    coalesce(sum(case when movement_type = 'contraction'  then mrr_change end), 0) as contraction_mrr,
    coalesce(sum(case when movement_type = 'churn'        then mrr_change end), 0) as churned_mrr,
    sum(mrr_change)                                                        as net_new_mrr,
    sum(mrr)                                                               as closing_mrr
from {{ ref('fct_mrr') }}
group by 1
