-- The MRR bridge must balance every month:
-- opening + new + expansion + reactivation + contraction + churned = closing, and opening = previous closing.
with b as (
    select *, lag(closing_mrr) over (order by month) as prev_closing
    from {{ ref('agg_mrr_bridge_monthly') }}
)
select *
from b
where abs(opening_mrr + new_mrr + expansion_mrr + reactivation_mrr + contraction_mrr + churned_mrr - closing_mrr) > 0.01
   or abs(coalesce(prev_closing, 0) - opening_mrr) > 0.01
