-- D03 | Marketing spend efficiency by campaign: CPM, CPC, CTR, cost per signup and cost per new customer.
-- Signups/customers are attributed to campaigns pro-rata to clicks within each channel-day (last-click proxy).
with camp as (
    select c.channel, c.campaign,
           sum(c.impressions) as impressions, sum(c.clicks) as clicks, sum(c.spend) as spend,
           sum(c.clicks * 1.0 / nullif(d.clicks, 0) * d.signups)        as signups_attr,
           sum(c.clicks * 1.0 / nullif(d.clicks, 0) * d.new_customers)  as customers_attr
    from marts.fct_campaign_daily c
    join marts.fct_marketing_daily d using (date, channel)
    group by 1, 2
)
select
    channel,
    campaign,
    round(spend, 0)                                       as spend,
    round(1000 * spend / impressions, 2)                  as cpm,
    round(spend / clicks, 2)                              as cpc,
    round(100.0 * clicks / impressions, 2)                as ctr_pct,
    round(signups_attr, 0)                                as signups_attributed,
    round(spend / signups_attr, 1)                        as cost_per_signup,
    round(customers_attr, 0)                              as customers_attributed,
    round(spend / customers_attr, 0)                      as cost_per_customer,
    rank() over (order by spend / customers_attr)         as efficiency_rank
from camp
order by efficiency_rank;
