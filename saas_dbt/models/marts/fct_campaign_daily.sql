-- Paid media at campaign grain (de-duplicated).
select
    spend_date as date,
    channel,
    campaign,
    impressions,
    clicks,
    spend,
    spend / nullif(clicks, 0)         as cpc,
    clicks / nullif(impressions, 0)   as ctr
from {{ ref('stg_marketing_spend') }}
