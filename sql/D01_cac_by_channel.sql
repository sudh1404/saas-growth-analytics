-- D01 | CAC by channel: full period and by quarter.
-- CAC = paid media spend / new paying customers acquired (first payment in the period) by that channel.
-- Blended CAC spreads all spend over all new customers incl. organic and referral.
with q as (
    select date_trunc('quarter', date) as quarter, channel,
           sum(spend) as spend, sum(new_customers) as new_customers
    from marts.fct_marketing_daily group by 1, 2
)
select
    cast(quarter as varchar)                                           as period,
    channel,
    round(spend, 0)                                                    as spend,
    new_customers,
    round(spend / nullif(new_customers, 0), 0)                         as cac
from q where spend > 0
union all
select 'all quarters (paid channels)', channel, round(sum(spend), 0), sum(new_customers),
       round(sum(spend) / sum(new_customers), 0)
from q where spend > 0 group by channel
union all
select 'all quarters (blended, all channels)', 'all', round(sum(spend), 0), sum(new_customers),
       round(sum(spend) / sum(new_customers), 0)
from q
order by period, channel;
