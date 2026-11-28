-- Paid media by day, channel and campaign. The ad-platform export re-delivers some rows: exact duplicates removed.
select distinct
    cast(spend_date as date)  as spend_date,
    lower(trim(channel))      as channel,
    campaign,
    impressions,
    clicks,
    cast(spend as double)     as spend
from {{ source('raw', 'marketing_spend') }}
