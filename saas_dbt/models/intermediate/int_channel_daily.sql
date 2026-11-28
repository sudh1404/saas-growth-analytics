-- Date x channel spine joining traffic, paid media, signups and new paying customers.
-- new_customers is attributed on the customer's first paid date (first subscription start) (used for period CAC).
with spine as (
    select cast(d as date) as date, c.channel
    from generate_series(date '2024-01-01', date '{{ var("snapshot_date") }}', interval 1 day) t(d)
    cross join (select distinct channel from {{ ref('stg_web_traffic') }}) c
),
traffic as (
    select traffic_date as date, channel, sum(visitors) as visitors, sum(pricing_page_views) as pricing_page_views
    from {{ ref('stg_web_traffic') }} group by 1, 2
),
media as (
    select spend_date as date, channel, sum(spend) as spend, sum(impressions) as impressions, sum(clicks) as clicks
    from {{ ref('stg_marketing_spend') }} group by 1, 2
),
signups as (
    select signup_date as date, acquisition_channel as channel, count(*) as signups
    from {{ ref('stg_accounts') }} group by 1, 2
),
customers as (
    select f.first_paid_date as date, a.acquisition_channel as channel, count(*) as new_customers
    from (select account_id, min(start_date) as first_paid_date
          from {{ ref('stg_subscriptions') }} group by 1) f
    join {{ ref('stg_accounts') }} a using (account_id)
    group by 1, 2
)
select
    s.date,
    s.channel,
    coalesce(t.visitors, 0)            as visitors,
    coalesce(t.pricing_page_views, 0)  as pricing_page_views,
    coalesce(g.signups, 0)             as signups,
    coalesce(m.impressions, 0)         as impressions,
    coalesce(m.clicks, 0)              as clicks,
    coalesce(m.spend, 0)               as spend,
    coalesce(c.new_customers, 0)       as new_customers
from spine s
left join traffic   t using (date, channel)
left join media     m using (date, channel)
left join signups   g using (date, channel)
left join customers c using (date, channel)
