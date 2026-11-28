-- D04 | Revenue contribution by acquisition channel: current MRR, share, collected revenue and return on spend.
select
    c.channel,
    c.channel_type,
    c.new_customers,
    c.current_mrr,
    round(100 * c.share_of_current_mrr, 1)                                  as share_of_mrr_pct,
    round(r.revenue_collected, 0)                                           as revenue_collected_to_date,
    round(c.spend, 0)                                                       as spend,
    round(r.revenue_collected / nullif(c.spend, 0), 2)                      as revenue_to_spend_ratio,
    round(c.current_mrr * 12 / nullif(c.spend, 0), 2)                       as arr_per_dollar_spent
from marts.agg_channel_performance c
join (select acquisition_channel as channel, sum(revenue_to_date) as revenue_collected
      from marts.dim_accounts group by 1) r using (channel)
order by c.current_mrr desc;
