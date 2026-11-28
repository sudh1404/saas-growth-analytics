-- E01 | Revenue concentration (Pareto) of active customers: share of collected revenue by revenue quartile,
-- and how many customers make up 50% / 80% of revenue.
select
    revenue_segment,
    count(*)                                                    as customers,
    round(sum(revenue_to_date), 0)                              as revenue_to_date,
    round(100.0 * sum(revenue_to_date) / sum(sum(revenue_to_date)) over (), 1) as revenue_share_pct,
    round(avg(current_mrr), 1)                                  as avg_current_mrr,
    round(avg(tenure_months), 1)                                as avg_tenure_months,
    (select count(*) from marts.agg_customer_segments where cumulative_revenue_share <= 0.5) as customers_for_50pct_revenue,
    (select count(*) from marts.agg_customer_segments where cumulative_revenue_share <= 0.8) as customers_for_80pct_revenue
from marts.agg_customer_segments
group by 1
order by 1;
